"""Exact admin submenu roots must reject stale callback suffixes."""

import unittest
from types import SimpleNamespace

from tests.test_admin_root_menu_callback_single_ack import (
    _Query,
    _load_functions,
    _main_menu_dependencies,
    _run_no_io,
)


ADMIN_ROOTS = (
    "admin_users",
    "admin_billing",
    "admin_queue",
    "admin_security_db",
    "admin_system_ops",
    "admin_handbook",
    "admin_provider",
    "admin_provider_worker",
    "admin_finance",
    "admin_packages",
    "freeze_queue",
)


class AdminSubmenuRootSuffixGuardTests(unittest.TestCase):
    def test_unproduced_admin_root_suffixes_alert_before_side_effects(self):
        for index, root in enumerate(ADMIN_ROOTS, start=1):
            with self.subTest(root=root):
                effects = []
                dependencies = _main_menu_dependencies(True, effects)
                dependencies.update({
                    "time": SimpleNamespace(perf_counter=lambda: 1.0),
                    "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
                })
                namespace = _load_functions("handle_menu_callback", **dependencies)
                query = _Query(991020 + index, f"menu|{root}|unsupported_context")
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
