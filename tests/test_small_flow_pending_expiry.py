"""Expired small-flow input states clear only their owning user's entry."""

import re
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _source_function(name):
    start = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\(", BOT_SOURCE)
    if not start:
        raise AssertionError(f"missing production helper: {name}")
    following = re.search(r"(?m)^(?:async )?def [A-Za-z_]\w*\(", BOT_SOURCE[start.end():])
    end = start.end() + following.start() if following else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end]


class SmallFlowPendingExpiryTests(unittest.TestCase):
    def test_expired_pending_getters_clear_only_their_own_users_state(self):
        clock = SimpleNamespace(now=100_000.0)
        namespace = {
            "USER_PENDING": {},
            "PENDING_ADMIN_TOOL_TEST": {},
            "time": SimpleNamespace(time=lambda: clock.now),
            "FREE_HUB_PENDING_TTL_SECONDS": 600,
            "VIDEO_DOWNLOADER_PENDING_TTL_SECONDS": 600,
            "ADMIN_TOOL_TEST_PENDING_TTL_SECONDS": 900,
            "SUPPORT_TICKET_TTL_SECONDS": 900,
            "DOC_TOOL_STATE_TTL_SECONDS": 600,
            "QUICK_MEDIA_PENDING_TTL_SECONDS": 600,
            "INTERNAL_ARCHIVE_TTL_SECONDS": 900,
        }
        cases = (
            ("free_hub_pending_key", "get_free_hub_pending", 701, 600, "dict", {"pending_action": "free_hub"}),
            ("video_downloader_pending_key", "get_video_downloader_pending", 702, 600, "dict", {"pending_action": "video_downloader"}),
            ("support_ticket_pending_key", "get_support_ticket_pending", 703, 900, "none", {"pending_action": "support_ticket"}),
            ("doc_tool_pending_key", "get_doc_tool_pending", 704, 600, "dict", {"doc_tool_current": "split_pdf"}),
            ("memory_guided_pending_key", "get_memory_guided_pending", 705, 600, "none", {"pending_action": "search"}),
            ("storage_addon_pending_key", "get_storage_addon_pending", 706, 600, "none", {"pending_action": "custom"}),
            ("internal_archive_pending_key", "get_internal_archive_pending", 707, 900, "none", {"pending_action": "internal_archive"}),
        )

        for key_function, getter, user_id, ttl, empty_kind, state in cases:
            with self.subTest(owner=key_function):
                exec(compile(_source_function(key_function), f"bot.py:{key_function}", "exec"), namespace)
                exec(compile(_source_function(getter), f"bot.py:{getter}", "exec"), namespace)
                key = namespace[key_function](user_id)
                unrelated_key = f"unrelated:{user_id}"
                unrelated_state = {"pending_action": "preserve"}
                namespace["USER_PENDING"][key] = {
                    **state,
                    "created_at_ts": clock.now - ttl - 1,
                }
                namespace["USER_PENDING"][unrelated_key] = unrelated_state.copy()

                result = namespace[getter](user_id)

                self.assertEqual(result, {} if empty_kind == "dict" else None)
                self.assertNotIn(key, namespace["USER_PENDING"])
                self.assertEqual(namespace["USER_PENDING"].get(unrelated_key), unrelated_state)
                namespace["USER_PENDING"].clear()

        exec(compile(_source_function("get_pending_admin_tool_test"), "bot.py:get_pending_admin_tool_test", "exec"), namespace)
        namespace["PENDING_ADMIN_TOOL_TEST"].update({
            708: {"tool": "asr", "expires_at": clock.now - 1},
            709: {"tool": "voice", "expires_at": clock.now + 60},
        })

        self.assertEqual(namespace["get_pending_admin_tool_test"](708), {})
        self.assertNotIn(708, namespace["PENDING_ADMIN_TOOL_TEST"])
        self.assertEqual(
            namespace["PENDING_ADMIN_TOOL_TEST"][709],
            {"tool": "voice", "expires_at": clock.now + 60},
        )


if __name__ == "__main__":
    unittest.main()
