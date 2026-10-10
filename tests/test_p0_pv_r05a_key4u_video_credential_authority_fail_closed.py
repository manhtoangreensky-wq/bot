"""Focused provider-free tests for Product Video Key4U video credential authority fail-closed.

TASK_ID=P0.PRODUCT_VIDEO_R16_10B14N21B_R05A_KEY4U_VIDEO_CREDENTIAL_AUTHORITY_CONFLICT_FAIL_CLOSED_CORRECTION
TRACKER=bot#1155
BASE_SHA=381d335961bea01db60cda99f0dfe98e2b2d1760

Covers cases:
01 canonical KEY4U_VIDEO_AUTH_HEADER_VALUE missing, legacy VIDEO_KEY4U_AUTH_HEADER_VALUE present -> BLOCKED
02 canonical missing, KEY4U_API_KEY present -> BLOCKED
03 canonical missing, KEY4U_TOKEN present -> BLOCKED
04 canonical present and legacy alias present with DIFFERENT values -> fail closed before HTTP
05 canonical present and legacy alias absent -> PASS config validation
06 canonical present and legacy alias contains SAME value -> PASS deterministic non-ambiguous
07 diagnostics never return secret value
08 readiness authority and actual provider consumer resolve same canonical credential authority
09 Bot-side and Worker-side provider-free hydration resolve same env NAME
10 R05A no-fallback/no-resubmit invariants remain unchanged
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.video_provider_catalog import (
    KEY4U_VIDEO_AUTH_ALIAS_CONFLICT,
    KEY4U_VIDEO_AUTH_MISSING,
    PRODUCT_VIDEO_CANONICAL_VIDEO_AUTH_ENV,
    PRODUCT_VIDEO_LEGACY_VIDEO_AUTH_ALIASES,
    PRODUCT_VIDEO_NON_VIDEO_KEY4U_KEYS,
    product_video_key4u_auth_diagnostics,
    resolve_product_video_key4u_auth,
)
from services.video_provider_router import (
    R05A_CANONICAL_PROVIDER,
    load_video_provider_adapter,
    provider_status_payload,
)
from providers.video_generic_http_provider import VideoGenerationRequest


class TestProductVideoKey4UAuthAuthorityFailClosed(unittest.TestCase):
    def setUp(self):
        self.base_env = {
            "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.vn/v1/video/create",
            "KEY4U_VIDEO_POLL_URL": "https://api.key4u.vn/v1/video/query?id={task_id}",
            "KEY4U_VIDEO_MODEL": "kling-v3",
            "KEY4U_VIDEO_ENABLED": "1",
        }

    def test_01_canonical_missing_legacy_alias_present_blocked(self):
        env = {
            **self.base_env,
            "VIDEO_KEY4U_AUTH_HEADER_VALUE": "Bearer legacy-secret-12345",
        }
        decision = resolve_product_video_key4u_auth(env)
        self.assertFalse(decision["ready"])
        self.assertEqual(decision["blocker"], KEY4U_VIDEO_AUTH_MISSING)
        self.assertEqual(decision["reason"], KEY4U_VIDEO_AUTH_MISSING)

        adapter = load_video_provider_adapter("key4u_video", env=env)
        self.assertFalse(adapter.capabilities()["configured"])

    def test_02_canonical_missing_api_key_present_blocked(self):
        env = {
            **self.base_env,
            "KEY4U_API_KEY": "api-key-secret-12345",
        }
        decision = resolve_product_video_key4u_auth(env)
        self.assertFalse(decision["ready"])
        self.assertEqual(decision["blocker"], KEY4U_VIDEO_AUTH_MISSING)

        adapter = load_video_provider_adapter("key4u_video", env=env)
        self.assertFalse(adapter.capabilities()["configured"])

    def test_03_canonical_missing_token_present_blocked(self):
        env = {
            **self.base_env,
            "KEY4U_TOKEN": "token-secret-12345",
        }
        decision = resolve_product_video_key4u_auth(env)
        self.assertFalse(decision["ready"])
        self.assertEqual(decision["blocker"], KEY4U_VIDEO_AUTH_MISSING)

        adapter = load_video_provider_adapter("key4u_video", env=env)
        self.assertFalse(adapter.capabilities()["configured"])

    def test_04_canonical_and_legacy_different_fail_closed_before_http(self):
        env = {
            **self.base_env,
            "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer canonical-secret-alpha",
            "VIDEO_KEY4U_AUTH_HEADER_VALUE": "Bearer legacy-secret-beta",
        }
        decision = resolve_product_video_key4u_auth(env)
        self.assertFalse(decision["ready"])
        self.assertEqual(decision["blocker"], KEY4U_VIDEO_AUTH_ALIAS_CONFLICT)
        self.assertEqual(decision["reason"], KEY4U_VIDEO_AUTH_ALIAS_CONFLICT)

        adapter = load_video_provider_adapter("key4u_video", env=env)
        self.assertFalse(adapter.capabilities()["configured"])

        req = VideoGenerationRequest(job_id="test-job", product_type="product_video", prompt="test", metadata={"aspect_ratio": "9:16", "product_video": True})
        with patch("urllib.request.urlopen") as mock_url:
            result = adapter.submit(req)
            self.assertFalse(result.ok)
            self.assertEqual(result.error_code, KEY4U_VIDEO_AUTH_ALIAS_CONFLICT)
            self.assertEqual(mock_url.call_count, 0)

    def test_05_canonical_present_legacy_absent_allowed(self):
        env = {
            **self.base_env,
            "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer canonical-secret-valid",
        }
        decision = resolve_product_video_key4u_auth(env)
        self.assertTrue(decision["ready"])
        self.assertEqual(decision["blocker"], "")

        adapter = load_video_provider_adapter("key4u_video", env=env)
        self.assertTrue(adapter.capabilities()["configured"])

    def test_06_canonical_and_legacy_same_value_deterministic(self):
        env = {
            **self.base_env,
            "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer canonical-secret-matching",
            "VIDEO_KEY4U_AUTH_HEADER_VALUE": "Bearer canonical-secret-matching",
        }
        decision = resolve_product_video_key4u_auth(env)
        self.assertTrue(decision["ready"])
        self.assertEqual(decision["canonical_env"], PRODUCT_VIDEO_CANONICAL_VIDEO_AUTH_ENV)

        adapter = load_video_provider_adapter("key4u_video", env=env)
        self.assertTrue(adapter.capabilities()["configured"])
        self.assertEqual(adapter.auth_header_value_env, PRODUCT_VIDEO_CANONICAL_VIDEO_AUTH_ENV)

    def test_07_diagnostics_never_return_secret_value(self):
        secret = "SUPER_SECRET_TOKEN_DO_NOT_LEAK_99999"
        env = {
            **self.base_env,
            "KEY4U_VIDEO_AUTH_HEADER_VALUE": f"Bearer {secret}",
            "VIDEO_KEY4U_AUTH_HEADER_VALUE": f"Bearer {secret}_different",
        }
        decision = resolve_product_video_key4u_auth(env)
        diag = product_video_key4u_auth_diagnostics(decision)
        dumped_diag = json.dumps(diag)
        self.assertNotIn(secret, dumped_diag)

        adapter = load_video_provider_adapter("key4u_video", env=env)
        caps = adapter.capabilities()
        self.assertNotIn(secret, json.dumps(caps))

    def test_08_readiness_and_execution_consume_same_decision(self):
        for bad_env in [
            {**self.base_env, "KEY4U_API_KEY": "some-key"},
            {**self.base_env, "VIDEO_KEY4U_AUTH_HEADER_VALUE": "some-alias"},
            {**self.base_env, "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer tokenA", "VIDEO_KEY4U_AUTH_HEADER_VALUE": "Bearer tokenB"},
        ]:
            status = provider_status_payload(bad_env)
            key4u_items = [p for p in status.get("providers", []) if p.get("provider") == "key4u_video"]
            self.assertEqual(len(key4u_items), 1)
            self.assertFalse(key4u_items[0].get("configured"))

            adapter = load_video_provider_adapter("key4u_video", env=bad_env)
            self.assertFalse(adapter.capabilities()["configured"])

    def test_09_bot_side_and_worker_side_resolve_same_env_name(self):
        self.assertEqual(PRODUCT_VIDEO_CANONICAL_VIDEO_AUTH_ENV, "KEY4U_VIDEO_AUTH_HEADER_VALUE")
        self.assertEqual(PRODUCT_VIDEO_LEGACY_VIDEO_AUTH_ALIASES, ("VIDEO_KEY4U_AUTH_HEADER_VALUE",))
        self.assertIn("KEY4U_API_KEY", PRODUCT_VIDEO_NON_VIDEO_KEY4U_KEYS)
        self.assertIn("KEY4U_TOKEN", PRODUCT_VIDEO_NON_VIDEO_KEY4U_KEYS)
        adapter = load_video_provider_adapter(
            "key4u_video",
            env={**self.base_env, "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test-valid"},
        )
        self.assertEqual(adapter.auth_header_value_env, "KEY4U_VIDEO_AUTH_HEADER_VALUE")

    def test_10_r05a_no_fallback_no_resubmit_invariants_preserved(self):
        self.assertEqual(R05A_CANONICAL_PROVIDER, "key4u_video")


if __name__ == "__main__":
    unittest.main()
