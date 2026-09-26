"""
R5 — Storyboard Final-Confirm Declared Count Preservation + Runtime Coverage Gate

MANDATORY_FIRST_RED_A: final-confirm declared count must survive partial materialization
MANDATORY_FIRST_RED_B: coverage validator must guard real execution path
"""
import copy
import importlib
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services import video_real_render_connector


# ============================================================================
# TEST CLASS A: Final-Confirm Declared Count Must Survive Partial Materialization
# ============================================================================
class TestFinalConfirmDeclaredCountPreservation(unittest.TestCase):
    """Prove that video_b14_prepare_project_for_invoice preserves declared
    scene_count even when fewer cards materialize."""

    def _call_prepare(self, session):
        """Import bot and call video_b14_prepare_project_for_invoice with mocks."""
        import bot

        def _mock_update_project(*_a, **kw):
            """Echo back asset_pack_json so test can verify scene_count."""
            ap = kw.get("asset_pack_json") or {}
            return {
                "project_id": 999,
                "asset_pack_json": ap,
                "scene_count": ap.get("scene_count"),
                "duration_seconds": ap.get("duration_seconds"),
                "scene_duration_seconds": ap.get("scene_duration_seconds"),
            }

        _invoice = {
            "scene_count": 1,
            "duration_seconds": 8,
            "scene_duration_seconds": 8,
            "quality_xu": 100,
            "routing_quality_tier": 100,
            "addons_disabled_by_package": False,
            "total_xu": 0,
        }

        with patch.object(bot, "video_uiflow3_handoff_from_session", return_value=False), \
             patch.object(bot, "video_b14_build_storyboard_for_session", return_value=MagicMock(to_dict=lambda: {})), \
             patch.object(bot, "video_b14_invoice_for_session", return_value=_invoice), \
             patch.object(bot, "video_b14_profile_id_for_session", return_value="test"), \
             patch.object(bot, "video_engine_product_type_for_session", return_value="storyboard_prompt"), \
             patch.object(bot, "video_final_output") as mock_vfo, \
             patch.object(bot, "product_video_logo_material_from_session", return_value={}), \
             patch.object(bot, "video_b14_is_admin_or_owner", return_value=False), \
             patch.object(bot, "get_video_session", return_value=session), \
             patch.object(bot, "create_video_project", return_value={"project_id": 999}), \
             patch.object(bot, "save_video_project_storyboard"), \
             patch.object(bot, "video_b14_creative_controls_to_storyboard", return_value={}), \
             patch.object(bot, "video_b14_worker_addon_plan_from_session", return_value={}), \
             patch.object(bot, "video_b14_sanitize_trial_addons", side_effect=lambda x, **kw: x), \
             patch.object(bot, "update_video_project", side_effect=_mock_update_project), \
             patch.object(bot, "save_video_session"), \
             patch("bot.os.getenv", side_effect=lambda k, d="": d):
            mock_vfo.route_for_product_type.return_value = {
                "adapter": "storyboard_scene_image_video_engine",
                "engine_family": "kling",
                "input_requirements": [],
            }
            result = bot.video_b14_prepare_project_for_invoice("test_user", session)
            return result

    def test_declared_2_materialize_1_scene_count_stays_2(self):
        """b14_scene_count=2 but only 1 card → scene_count must be 2, not 1."""
        session = {
            "topic": "test",
            "draft": {
                "b14_scene_count": 2,
                "b14_scene_seconds": 8,
                "scene_cards": [
                    {"scene_index": 1, "prompt": "Scene 1", "image_path": "/img/1.png"},
                ],
                "b14_storyboard_plan": {"scenes": []},
                "b14_aspect_ratio": "9:16",
            },
        }
        result = self._call_prepare(session)
        asset_pack = result.get("asset_pack_json") or result.get("asset_pack") or {}
        sc = asset_pack.get("scene_count", result.get("scene_count"))
        self.assertEqual(sc, 2, f"Declared scene_count=2 must survive; got {sc}")
        self.assertEqual(
            asset_pack.get("duration_seconds", result.get("duration_seconds")),
            16,
            "duration must be 2 * 8 = 16",
        )

    def test_declared_3_materialize_2_scene_count_stays_3(self):
        """b14_scene_count=3 but only 2 cards → scene_count must be 3."""
        session = {
            "topic": "test",
            "draft": {
                "b14_scene_count": 3,
                "b14_scene_seconds": 8,
                "scene_cards": [
                    {"scene_index": 1, "prompt": "S1", "image_path": "/img/1.png"},
                    {"scene_index": 2, "prompt": "S2", "image_path": "/img/2.png"},
                ],
                "b14_storyboard_plan": {"scenes": []},
                "b14_aspect_ratio": "9:16",
            },
        }
        result = self._call_prepare(session)
        asset_pack = result.get("asset_pack_json") or result.get("asset_pack") or {}
        sc = asset_pack.get("scene_count", result.get("scene_count"))
        self.assertEqual(sc, 3, f"Declared scene_count=3 must survive; got {sc}")
        self.assertEqual(
            asset_pack.get("duration_seconds", result.get("duration_seconds")),
            24,
            "duration must be 3 * 8 = 24",
        )

    def test_no_declared_count_falls_back_to_len_cards(self):
        """Without b14_scene_count, len(materialized_cards) is authority."""
        session = {
            "topic": "test",
            "draft": {
                "scene_cards": [
                    {"scene_index": 1, "prompt": "S1"},
                    {"scene_index": 2, "prompt": "S2"},
                ],
                "b14_storyboard_plan": {"scenes": []},
                "b14_aspect_ratio": "9:16",
            },
        }
        result = self._call_prepare(session)
        asset_pack = result.get("asset_pack_json") or result.get("asset_pack") or {}
        sc = asset_pack.get("scene_count", result.get("scene_count"))
        self.assertEqual(sc, 2, f"No declared count → len(cards)=2; got {sc}")

    def test_declared_scene_seconds_and_duration_correct(self):
        """Verify scene_duration_seconds = 8, duration_seconds = declared * 8."""
        session = {
            "topic": "test",
            "draft": {
                "b14_scene_count": 5,
                "b14_scene_seconds": 8,
                "scene_cards": [
                    {"scene_index": 1, "prompt": "S1", "image_path": "/img/1.png"},
                ],
                "b14_storyboard_plan": {"scenes": []},
                "b14_aspect_ratio": "9:16",
            },
        }
        result = self._call_prepare(session)
        asset_pack = result.get("asset_pack_json") or result.get("asset_pack") or {}
        sc = asset_pack.get("scene_count", result.get("scene_count"))
        self.assertEqual(sc, 5)
        self.assertEqual(asset_pack.get("scene_duration_seconds", result.get("scene_duration_seconds")), 8)
        self.assertEqual(asset_pack.get("duration_seconds", result.get("duration_seconds")), 40)


# ============================================================================
# TEST CLASS B: Coverage Validator Must Guard Real Execution Path
# ============================================================================
class TestCoverageValidatorRuntimeWiring(unittest.TestCase):
    """Prove that validate_storyboard_scene_coverage() is called in the
    canonical render path and blocks provider dispatch on invalid coverage."""

    def _build_storyboard_job(self, scene_cards, scene_count=2):
        """Build a minimal storyboard job dict."""
        return {
            "id": "test_job_r5",
            "job_id": "test_job_r5",
            "user_id": "u_test",
            "source": "product_video",
            "product_video": True,
            "product_type": "storyboard_prompt",
            "engine_adapter": "storyboard_scene_image_video_engine",
            "orchestration_mode": "per_scene_8s",
            "provider_orchestration_mode": "per_scene_8s",
            "required_capability": "image_to_video",
            "provider_call": True,
            "real_renderer_required": True,
            "render_mode": "real",
            "test_pattern": False,
            "scene_count": scene_count,
            "scene_duration_seconds": 8,
            "duration_seconds": scene_count * 8,
            "scene_cards": scene_cards,
            "pinned_wire_model": "kling-v3",
            "selected_model": "kling-v3",
            "model": "kling-v3",
            "selected_provider": "key4u_video",
            "provider_order": "key4u_video",
            "provider_chain": ["key4u_video"],
            "asset_pack": {
                "scene_cards": scene_cards,
                "scene_count": scene_count,
            },
        }

    def _run_render_expect_coverage_error(self, job):
        """Call render_real_video_job expecting a coverage validation failure.
        Returns the error diagnostics dict."""
        import tempfile
        work_dir = tempfile.mkdtemp(prefix="r5_test_")
        # Patch provider readiness to look ready (so we reach the coverage gate)
        with patch.object(video_real_render_connector, "real_video_provider_readiness",
                          return_value={"ok": True, "providers": [{"name": "key4u_video", "ready": True}]}), \
             patch.object(video_real_render_connector, "_provider_candidates_for_capability",
                          return_value=[{"provider": "key4u_video"}]), \
             patch.object(video_real_render_connector, "product_video_materialize_addons",
                          return_value={"ok": True, "strict": False}), \
             patch.object(video_real_render_connector, "video_final_output") as mock_vfo:
            mock_vfo.route_for_product_type.return_value = {
                "adapter": "storyboard_scene_image_video_engine",
                "engine_family": "kling",
                "fallback_capability": "",
            }
            mock_vfo.product_type_from_project.return_value = "storyboard_prompt"
            mock_vfo.normalize_video_product_type.return_value = "storyboard_prompt"
            try:
                result = video_real_render_connector.render_real_video_job(job, work_dir)
                # If it returns instead of raising, check result for coverage blocker
                if isinstance(result, dict):
                    if result.get("no_charge") and "coverage" in str(result.get("blocker") or result.get("provider_error") or "").lower():
                        return result
                self.fail(
                    f"Expected coverage validation error but render returned: "
                    f"ok={result.get('ok')}, blocker={result.get('blocker')}"
                )
            except video_real_render_connector.RealVideoRenderError as e:
                diag = e.diagnostics if hasattr(e, "diagnostics") else {}
                return diag
            except Exception as e:
                # Check if it's a coverage-related error
                err_str = str(e).lower()
                if "coverage" in err_str or "scene" in err_str:
                    return {"error": str(e), "provider_attempted": False, "no_charge": True}
                raise

    def test_missing_scene_blocks_provider(self):
        """declared_count=2 but only scene_index=1 → provider must NOT be called."""
        cards = [{"scene_index": 1, "prompt": "S1", "image_path": "/img/1.png"}]
        job = self._build_storyboard_job(cards, scene_count=2)
        diag = self._run_render_expect_coverage_error(job)
        self.assertFalse(diag.get("provider_submit_called", True),
                         "Provider must not be called with incomplete coverage")
        self.assertTrue(diag.get("no_charge", False),
                        "Must be no_charge on coverage failure")

    def test_duplicate_scene_index_blocks_provider(self):
        """Two cards both scene_index=1, declared_count=2 → provider blocked."""
        cards = [
            {"scene_index": 1, "prompt": "S1a", "image_path": "/img/1a.png"},
            {"scene_index": 1, "prompt": "S1b", "image_path": "/img/1b.png"},
        ]
        job = self._build_storyboard_job(cards, scene_count=2)
        diag = self._run_render_expect_coverage_error(job)
        self.assertFalse(diag.get("provider_submit_called", True))
        self.assertTrue(diag.get("no_charge", False))

    def test_out_of_range_scene_index_blocks_provider(self):
        """scene_index=99, declared_count=2 → provider blocked."""
        cards = [
            {"scene_index": 1, "prompt": "S1", "image_path": "/img/1.png"},
            {"scene_index": 99, "prompt": "S99", "image_path": "/img/99.png"},
        ]
        job = self._build_storyboard_job(cards, scene_count=2)
        diag = self._run_render_expect_coverage_error(job)
        self.assertFalse(diag.get("provider_submit_called", True))
        self.assertTrue(diag.get("no_charge", False))

    def test_card_without_scene_index_blocks_provider(self):
        """Card missing scene_index entirely → provider blocked."""
        cards = [
            {"scene_index": 1, "prompt": "S1", "image_path": "/img/1.png"},
            {"prompt": "no index card", "image_path": "/img/x.png"},
        ]
        job = self._build_storyboard_job(cards, scene_count=2)
        diag = self._run_render_expect_coverage_error(job)
        self.assertFalse(diag.get("provider_submit_called", True))
        self.assertTrue(diag.get("no_charge", False))

    def test_valid_coverage_does_not_block(self):
        """Complete valid coverage → should NOT raise coverage error."""
        cards = [
            {"scene_index": 1, "prompt": "S1", "image_path": "/img/1.png"},
            {"scene_index": 2, "prompt": "S2", "image_path": "/img/2.png"},
        ]
        job = self._build_storyboard_job(cards, scene_count=2)
        import tempfile
        work_dir = tempfile.mkdtemp(prefix="r5_test_valid_")
        with patch.object(video_real_render_connector, "real_video_provider_readiness",
                          return_value={"ok": True, "providers": [{"name": "key4u_video", "ready": True}]}), \
             patch.object(video_real_render_connector, "_provider_candidates_for_capability",
                          return_value=[{"provider": "key4u_video"}]), \
             patch.object(video_real_render_connector, "product_video_materialize_addons",
                          return_value={"ok": True, "strict": False}), \
             patch.object(video_real_render_connector, "video_final_output") as mock_vfo, \
             patch.object(video_real_render_connector, "_run_per_scene_provider_orchestrator",
                          return_value={"ok": True, "status": "completed"}) as mock_orch:
            mock_vfo.route_for_product_type.return_value = {
                "adapter": "storyboard_scene_image_video_engine",
                "engine_family": "kling",
                "fallback_capability": "",
            }
            mock_vfo.product_type_from_project.return_value = "storyboard_prompt"
            mock_vfo.normalize_video_product_type.return_value = "storyboard_prompt"
            try:
                result = video_real_render_connector.render_real_video_job(job, work_dir)
                # If we reach the orchestrator mock, coverage gate passed
                if mock_orch.called:
                    return  # SUCCESS: coverage gate did not block valid coverage
                # Result may contain coverage info if validator ran
                blocker = str(result.get("blocker") or "")
                if "coverage" in blocker.lower():
                    self.fail("Valid coverage should not be blocked")
            except video_real_render_connector.RealVideoRenderError as e:
                diag = e.diagnostics if hasattr(e, "diagnostics") else {}
                blocker = str(diag.get("blocker") or str(e))
                if "coverage" in blocker.lower():
                    self.fail(f"Valid coverage should not be blocked: {blocker}")
                # Other errors (e.g. file not found) are acceptable — we only care
                # that coverage gate didn't fire


if __name__ == "__main__":
    unittest.main()
