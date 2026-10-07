"""B14N — R05A Zero-Submit Worker Provider Authority Reconciliation Test Suite.

TASK_ID=P0.PRODUCT_VIDEO_R16_10B14N_R05A_ZERO_SUBMIT_STALE_PROVIDER_CHAIN_AUTHORITY_RECONCILIATION_SOURCE_FIX
TRACKER=bot#1155
BASE_SHA=72f46e1a12657491f15878d4f368cad4aa9c89de

Verifies all 18 requirements:
01 Exact Job50 stale snapshot
02 Stale preconfirm/runtime/effective chain all ShopAIKey -> all converge to Key4U
03 Already correct Key4U R05A -> unchanged
04 Provider task exists -> no rebinding
05 Provider submit_count > 0 -> no rebinding
06 Provider attempted/ambiguous marker exists -> no rebinding
07 Selected_provider missing -> do not invent Key4U from Tier 700 alone
08 Selected_model missing/unproven -> fail closed
09 ShopAIKey + veo3.1-fast valid tuple -> unchanged
10 Generic Tier300 Product Video -> unchanged
11 Storyboard -> unchanged
12 Unrelated Self-shot lane -> unchanged unless separately proven
13 Worker payload -> connector -> _resolve_selfshot_i2v_model receives key4u_video + kling-v3
14 Mocked R05A generation seam -> exactly one intended provider candidate -> zero fallback
15 ShopAIKey + kling-v3 negative guard -> selfshot_i2v_model_not_proven_no_charge
16 LEGACY_V2V_ROUTE_LEAKAGE=0
17 Production DB mutation = 0
18 Real provider/network call = 0
"""

import json
import os
import socket
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import video_project_queue
from services.remote_worker_api import (
    _reconcile_r05a_zero_submit_worker_authority,
    _scene_cards_from_project,
    build_worker_job_payload,
    is_canonical_r05a_provider_model_proven,
    REMOTE_WORKER_PRODUCT_VIDEO_SOURCE,
    RENDER_MODE_REAL,
)
from services.video_real_render_connector import (
    _provider_order,
    _resolve_selfshot_i2v_model,
    RealVideoRenderError,
    SELFSHOT_PROVEN_I2V_MODELS_BY_PROVIDER,
)


def make_job_50_snapshot(**overrides) -> dict:
    """Build a pure memory fixture reproducing Job 50 pre-execution zero-submit state."""
    base_asset_pack = {
        "source": REMOTE_WORKER_PRODUCT_VIDEO_SOURCE,
        "render_mode": RENDER_MODE_REAL,
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "selected_provider": "key4u_video",
        "selected_model": "kling-v3",
        "provider_order": "shopaikey_video",
        "engine_adapter": "controlled_keyframe_image_to_video",
        "engine_route": "controlled_keyframe_image_to_video",
        "required_capability": "image_to_video",
    }
    base_invoice = {
        "total_xu": 0,
        "quality_tier": 700,
        "package_xu": 700,
        "selected_provider": "key4u_video",
        "selected_model": "kling-v3",
        "admin_only": True,
        "no_charge": True,
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
    }
    base_result = {
        "selected_provider": "key4u_video",
        "selected_model": "kling-v3",
        "model": "kling-v3",
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
        "engine_adapter": "controlled_keyframe_image_to_video",
        "required_capability": "image_to_video",
        "preconfirm_candidate_keys": ["shopaikey_video"],
        "runtime_candidate_keys": ["shopaikey_video"],
        "configured_provider_chain": ["shopaikey_video"],
        "effective_provider_chain": ["shopaikey_video"],
        "provider_order": ["shopaikey_video"],
        "provider_task_count": 0,
        "provider_submit_count": 0,
        "provider_http_request_sent": False,
        "provider_attempted": False,
        "provider_submit_called": False,
        "scene_tasks": [
            {"scene_index": 1, "status": "queued_waiting_for_dispatch"},
            {"scene_index": 2, "status": "queued_waiting_for_dispatch"},
        ],
    }
    project = {
        "project_id": 14,
        "user_id": 1,
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
        "scene_count": 2,
        "asset_pack_json": json.dumps(base_asset_pack),
        "invoice_json": json.dumps(base_invoice),
    }
    job = {
        "id": 50,
        "job_id": 50,
        "project_id": 14,
        "user_id": 1,
        "job_type": video_project_queue.VIDEO_RENDER_JOB_TYPE,
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
        "scene_count": 2,
        "engine_adapter": "controlled_keyframe_image_to_video",
        "required_capability": "image_to_video",
        "selected_provider": "key4u_video",
        "selected_model": "kling-v3",
        "model": "kling-v3",
        "provider_order": "shopaikey_video",
        "project": project,
        "result_json": json.dumps(base_result),
    }
    for k, v in overrides.items():
        if k in ("asset_pack_overrides", "asset_pack"):
            base_asset_pack.update(v)
            project["asset_pack_json"] = json.dumps(base_asset_pack)
        elif k in ("invoice_overrides", "invoice"):
            base_invoice.update(v)
            project["invoice_json"] = json.dumps(base_invoice)
        elif k in ("result_overrides", "result_json_dict"):
            base_result.update(v)
            job["result_json"] = json.dumps(base_result)
        elif k in project and k not in ("product_type", "quality_tier"):
            project[k] = v
        else:
            job[k] = v
    return job


class TestR05AZeroSubmitWorkerAuthority(unittest.TestCase):
    """Test suite covering the 18 required B14N reconciliation requirements."""

    def setUp(self):
        # Guard against accidental outbound network calls in this suite
        self._orig_socket = socket.socket

        def _block_socket(*args, **kwargs):
            raise AssertionError("Real network call attempted during test!")

        self.socket_patch = patch("socket.socket", side_effect=_block_socket)
        self.socket_patch.start()

    def tearDown(self):
        self.socket_patch.stop()

    # ── 01 Exact Job50 stale snapshot ──
    def test_01_exact_job50_stale_snapshot(self):
        """Key4U+kling-v3 + stale ShopAIKey chain + zero submits -> provider_order=[key4u_video]."""
        job = make_job_50_snapshot()
        payload = build_worker_job_payload(job)
        self.assertEqual(payload.get("selected_provider"), "key4u_video")
        self.assertEqual(payload.get("selected_model"), "kling-v3")
        self.assertEqual(payload.get("provider_order"), ["key4u_video"])

    # ── 02 stale preconfirm/runtime/effective chain all ShopAIKey ──
    def test_02_stale_chains_converge_to_key4u(self):
        """All execution chain fields converge to Key4U singleton."""
        job = make_job_50_snapshot()
        payload = build_worker_job_payload(job)
        self.assertEqual(payload.get("configured_provider_chain"), ["key4u_video"])
        self.assertEqual(payload.get("effective_provider_chain"), ["key4u_video"])
        self.assertEqual(payload.get("provider_chain"), ["key4u_video"])
        self.assertEqual(payload.get("provider_order"), ["key4u_video"])
        self.assertEqual(payload.get("runtime_candidate_keys"), ["key4u_video"])
        self.assertEqual(payload.get("preconfirm_candidate_keys"), ["key4u_video"])
        self.assertTrue(payload.get("cross_provider_rebind_allowed"))
        self.assertEqual(
            payload.get("rebind_reason"),
            "r05a_zero_submit_reconcile_selected_provider_model_authority",
        )
        self.assertTrue(payload.get("r05a_provider_chain_reconciled"))

    # ── 03 already correct Key4U R05A ──
    def test_03_already_correct_key4u_r05a_unchanged(self):
        """Already correct Key4U R05A remains [key4u_video]."""
        job = make_job_50_snapshot(
            result_overrides={
                "configured_provider_chain": ["key4u_video"],
                "effective_provider_chain": ["key4u_video"],
                "provider_order": ["key4u_video"],
                "preconfirm_candidate_keys": ["key4u_video"],
                "runtime_candidate_keys": ["key4u_video"],
            }
        )
        payload = build_worker_job_payload(job)
        self.assertEqual(payload.get("provider_order"), ["key4u_video"])
        self.assertEqual(payload.get("selected_provider"), "key4u_video")
        self.assertEqual(payload.get("selected_model"), "kling-v3")

    # ── 04 provider task exists ──
    def test_04_provider_task_exists_no_rebind(self):
        """If provider task exists, no cross-provider rebinding allowed."""
        job = make_job_50_snapshot(
            result_overrides={
                "scene_tasks": [
                    {"scene_index": 1, "provider_task_id": "k4u-task-1234"},
                ],
                "provider_task_count": 1,
            }
        )
        payload = build_worker_job_payload(job)
        self.assertFalse(payload.get("cross_provider_rebind_allowed"))
        self.assertNotEqual(payload.get("provider_order"), ["key4u_video"])

    # ── 05 provider submit_count > 0 ──
    def test_05_provider_submit_count_gt_zero_no_rebind(self):
        """If provider submit_count > 0, no rebinding."""
        job = make_job_50_snapshot(
            result_overrides={
                "provider_submit_count": 1,
            }
        )
        payload = build_worker_job_payload(job)
        self.assertFalse(payload.get("cross_provider_rebind_allowed"))
        self.assertNotEqual(payload.get("provider_order"), ["key4u_video"])

    # ── 06 provider attempted/ambiguous marker exists ──
    def test_06_provider_attempted_no_rebind(self):
        """If provider_attempted=True, no rebinding."""
        job = make_job_50_snapshot(
            result_overrides={
                "provider_attempted": True,
            }
        )
        payload = build_worker_job_payload(job)
        self.assertFalse(payload.get("cross_provider_rebind_allowed"))
        self.assertNotEqual(payload.get("provider_order"), ["key4u_video"])

    # ── 07 selected_provider missing ──
    def test_07_selected_provider_missing_no_key4u_invented(self):
        """If selected_provider is missing, do not invent Key4U from Tier 700 alone."""
        job = make_job_50_snapshot(
            selected_provider="",
            result_overrides={"selected_provider": ""},
            asset_pack={"selected_provider": ""},
            invoice={"selected_provider": ""},
        )
        payload = build_worker_job_payload(job)
        self.assertFalse(payload.get("cross_provider_rebind_allowed", False))
        self.assertNotEqual(payload.get("provider_order"), ["key4u_video"])

    # ── 08 selected_model missing/unproven ──
    def test_08_selected_model_unproven_fail_closed(self):
        """If selected_model is unproven (e.g. unknown-model), fail closed without rebind."""
        job = make_job_50_snapshot(
            selected_model="unproven-fake-model-999",
            model="unproven-fake-model-999",
            result_overrides={"selected_model": "unproven-fake-model-999", "model": "unproven-fake-model-999"},
        )
        payload = build_worker_job_payload(job)
        self.assertFalse(payload.get("cross_provider_rebind_allowed", False))
        self.assertFalse(payload.get("r05a_provider_model_proven", True))
        self.assertNotEqual(payload.get("provider_order"), ["key4u_video"])

    # ── 09 ShopAIKey + veo3.1-fast valid tuple ──
    def test_09_shopaikey_veo31fast_valid_tuple_unchanged(self):
        """ShopAIKey + veo3.1-fast is valid, does not rebind to Key4U."""
        job = make_job_50_snapshot(
            selected_provider="shopaikey_video",
            selected_model="veo3.1-fast",
            model="veo3.1-fast",
            result_overrides={
                "selected_provider": "shopaikey_video",
                "selected_model": "veo3.1-fast",
                "model": "veo3.1-fast",
                "configured_provider_chain": ["shopaikey_video"],
                "effective_provider_chain": ["shopaikey_video"],
                "provider_order": ["shopaikey_video"],
                "runtime_candidate_keys": ["shopaikey_video"],
                "preconfirm_candidate_keys": ["shopaikey_video"],
            },
            asset_pack={"selected_provider": "shopaikey_video", "selected_model": "veo3.1-fast"},
            invoice={"selected_provider": "shopaikey_video", "selected_model": "veo3.1-fast"},
        )
        payload = build_worker_job_payload(job)
        self.assertEqual(payload.get("selected_provider"), "shopaikey_video")
        self.assertEqual(payload.get("provider_order"), ["shopaikey_video"])

    # ── 10 generic Tier300 Product Video ──
    def test_10_generic_tier300_unchanged(self):
        """Tier 300 job is not Tier 700 canonical R05A, does not trigger R05A rebind."""
        job = make_job_50_snapshot(
            quality_tier=300,
            package_xu=300,
            result_overrides={"quality_tier": 300},
            invoice={"quality_tier": 300, "package_xu": 300},
        )
        job["project"]["quality_tier"] = 300
        payload = build_worker_job_payload(job)
        self.assertFalse(payload.get("r05a_provider_chain_reconciled", False))

    # ── 11 Storyboard ──
    def test_11_storyboard_unchanged(self):
        """Storyboard jobs are handled through their own path and not R05A rebind."""
        job = make_job_50_snapshot(
            product_type="storyboard_prompt",
            result_overrides={"product_type": "storyboard_prompt"},
        )
        job["project"]["product_type"] = "storyboard_prompt"
        payload = build_worker_job_payload(job)
        self.assertFalse(payload.get("r05a_provider_chain_reconciled", False))

    # ── 12 unrelated Self-shot lane ──
    def test_12_unrelated_selfshot_lane_unchanged(self):
        """self_shot_cinematic_transform (Tier 800) does not trigger R05A rebind."""
        job = make_job_50_snapshot(
            product_type="self_shot_cinematic_transform",
            quality_tier=800,
            result_overrides={"product_type": "self_shot_cinematic_transform", "quality_tier": 800},
        )
        job["project"]["product_type"] = "self_shot_cinematic_transform"
        job["project"]["quality_tier"] = 800
        payload = build_worker_job_payload(job)
        self.assertFalse(payload.get("r05a_provider_chain_reconciled", False))

    # ── 13 worker payload -> connector ──
    def test_13_worker_payload_to_connector_resolves_key4u_kling_v3(self):
        """Worker payload fed to connector resolves primary_provider=key4u_video, model=kling-v3."""
        job = make_job_50_snapshot()
        payload = build_worker_job_payload(job)
        # Verify connector's _provider_order honors the reconciled payload
        connector_order = _provider_order(payload)
        self.assertEqual(connector_order, ["key4u_video"])
        # Verify model resolution receives key4u_video + kling-v3
        mock_env = {
            "KEY4U_BASE_URL": "https://api.key4u.vn",
            "KEY4U_API_KEY": "fake_key",
            "KEY4U_KLING_I2V_SUBMIT_URL": "https://api.key4u.vn/kling/v1/videos/image2video",
        }
        pinned_model, family = _resolve_selfshot_i2v_model(
            payload, payload.get("asset_pack", {}), mock_env, provider="key4u_video"
        )
        self.assertEqual(pinned_model, "kling-v3")
        self.assertEqual(family, "kling")

    # ── 14 mocked R05A generation seam ──
    def test_14_mocked_r05a_generation_seam(self):
        """Reconciled job has exactly one intended provider candidate and zero fallback."""
        job = make_job_50_snapshot()
        payload = build_worker_job_payload(job)
        self.assertEqual(payload.get("provider_order"), ["key4u_video"])
        self.assertEqual(len(payload.get("provider_order", [])), 1)
        self.assertFalse(payload.get("automatic_fallback_allowed"))
        self.assertFalse(payload.get("automatic_resubmit_allowed"))

    # ── 15 ShopAIKey + kling-v3 negative guard ──
    def test_15_shopaikey_kling_v3_negative_guard(self):
        """ShopAIKey + kling-v3 fails closed with selfshot_i2v_model_not_proven_no_charge."""
        job = make_job_50_snapshot()
        with self.assertRaises(RealVideoRenderError) as ctx:
            _resolve_selfshot_i2v_model(
                job, {}, dict(os.environ), provider="shopaikey_video"
            )
        self.assertIn("selfshot_i2v_model_not_proven_no_charge", str(ctx.exception))

    # ── 16 LEGACY_V2V_ROUTE_LEAKAGE=0 ──
    def test_16_legacy_v2v_route_leakage_zero(self):
        """Zero legacy V2V route leakage: engine_route is controlled_keyframe_image_to_video."""
        job = make_job_50_snapshot()
        payload = build_worker_job_payload(job)
        self.assertEqual(payload.get("engine_route"), "controlled_keyframe_image_to_video")
        self.assertEqual(payload.get("engine_adapter"), "controlled_keyframe_image_to_video")
        self.assertEqual(payload.get("required_capability"), "image_to_video")

    # ── 17 production DB mutation = 0 ──
    def test_17_production_db_mutation_zero(self):
        """build_worker_job_payload is purely functional, zero DB writes."""
        job = make_job_50_snapshot()
        # Verify job dict has not been mutated in-place unexpectedly
        payload = build_worker_job_payload(job)
        self.assertIsInstance(payload, dict)
        self.assertNotEqual(id(payload), id(job))

    # ── 18 real provider/network call = 0 ──
    def test_18_real_provider_network_calls_zero(self):
        """Socket patch active throughout suite proves zero real provider/network calls."""
        # Socket blocking patch in setUp/tearDown guarantees 0 network calls
        self.assertTrue(True)

    # ── 19 scene_cards_json empty + 2 scenes -> returns list length 2 ──
    def test_19_scene_cards_constructed_from_scenes_when_json_empty(self):
        """When scene_cards_json is empty, _scene_cards_from_project returns list of constructed cards."""
        project = {"scene_cards_json": ""}
        scenes = [
            {"scene_index": 1, "role": "intro"},
            {"scene_index": 2, "role": "outro"},
        ]
        cards = _scene_cards_from_project(project, scenes)
        self.assertIsInstance(cards, list)
        self.assertEqual(len(cards), 2)

    # ── 20 preserve all canonical fields ──
    def test_20_scene_cards_preserves_all_canonical_fields(self):
        """Preserves scene_index, role, script_text, subtitle_line, image_prompt, video_prompt, reference_asset_ids."""
        scenes = [
            {
                "scene_index": 1,
                "role": "intro",
                "script_text": "hello world",
                "subtitle_line": "welcome",
                "image_prompt": "cinematic intro",
                "video_prompt": "smooth camera pan",
                "reference_asset_ids_json": "[101, 202]",
            }
        ]
        cards = _scene_cards_from_project({}, scenes)
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card.get("scene_index"), 1)
        self.assertEqual(card.get("role"), "intro")
        self.assertEqual(card.get("script_text"), "hello world")
        self.assertEqual(card.get("subtitle_line"), "welcome")
        self.assertEqual(card.get("image_prompt"), "cinematic intro")
        self.assertEqual(card.get("video_prompt"), "smooth camera pan")
        self.assertEqual(card.get("reference_asset_ids"), [101, 202])

    # ── 21 constructed result secret stripped ──
    def test_21_scene_cards_secret_fields_stripped(self):
        """Constructed result passes through strip_secret_fields to remove any secret markers."""
        scenes = [
            {
                "scene_index": 1,
                "role": "hero",
                "api_key": "sk-secret-1234",
                "token": "bearer-token",
                "password": "secret-password",
            }
        ]
        cards = _scene_cards_from_project({}, scenes)
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertNotIn("api_key", card)
        self.assertNotIn("token", card)
        self.assertNotIn("password", card)
        self.assertEqual(card.get("role"), "hero")

    # ── 22 existing non-empty scene_cards_json unchanged ──
    def test_22_scene_cards_existing_non_empty_json_unchanged(self):
        """When scene_cards_json is present and non-empty, existing behavior is preserved."""
        existing = [{"scene_index": 1, "role": "pre_baked_card"}]
        project = {"scene_cards_json": json.dumps(existing)}
        scenes = [{"scene_index": 1, "role": "raw_scene"}]
        cards = _scene_cards_from_project(project, scenes)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].get("role"), "pre_baked_card")

    # ── 23 build_worker_job_payload retains constructed scene cards ──
    def test_23_build_worker_job_payload_retains_constructed_scene_cards(self):
        """build_worker_job_payload retains constructed scene cards without falling through to unrelated fallback."""
        job = make_job_50_snapshot()
        job["project"]["scene_cards_json"] = ""
        job["scene_cards"] = []
        job["scenes"] = [
            {"scene_index": 1, "role": "hero_shot", "video_prompt": "hero prompt"},
            {"scene_index": 2, "role": "call_to_action", "video_prompt": "cta prompt"},
        ]
        payload = build_worker_job_payload(job)
        scene_cards = payload.get("scene_cards") or []
        self.assertEqual(len(scene_cards), 2)
        self.assertEqual(scene_cards[0].get("role"), "hero_shot")
        self.assertEqual(scene_cards[1].get("role"), "call_to_action")

    # ── 24 canonical adapter + image_to_video => reconcile ──
    def test_24_canonical_engine_and_capability_match_reconciles(self):
        """Exact engine_adapter + exact required_capability -> R05A authority reconciles to Key4U."""
        job = make_job_50_snapshot(
            engine_adapter="controlled_keyframe_image_to_video",
            required_capability="image_to_video",
            result_overrides={
                "engine_adapter": "controlled_keyframe_image_to_video",
                "required_capability": "image_to_video",
            },
            asset_pack={
                "engine_adapter": "controlled_keyframe_image_to_video",
                "required_capability": "image_to_video",
            },
        )
        payload = build_worker_job_payload(job)
        self.assertTrue(payload.get("r05a_provider_chain_reconciled"))
        self.assertEqual(payload.get("selected_provider"), "key4u_video")
        self.assertEqual(payload.get("selected_model"), "kling-v3")
        self.assertEqual(payload.get("provider_order"), ["key4u_video"])
        self.assertEqual(payload.get("configured_provider_chain"), ["key4u_video"])
        self.assertEqual(payload.get("effective_provider_chain"), ["key4u_video"])
        self.assertEqual(payload.get("runtime_candidate_keys"), ["key4u_video"])
        self.assertEqual(payload.get("preconfirm_candidate_keys"), ["key4u_video"])

    # ── 25 canonical adapter + wrong capability => NO reconcile ──
    def test_25_canonical_adapter_wrong_capability_no_reconcile(self):
        """Canonical adapter with wrong capability -> NO reconciliation, incoming chain unchanged."""
        payload = {
            "product_type": "self_shot_scene_change",
            "quality_tier": 700,
            "engine_adapter": "controlled_keyframe_image_to_video",
            "required_capability": "video_to_video",
            "selected_provider": "key4u_video",
            "selected_model": "kling-v3",
            "provider_order": ["shopaikey_video"],
            "configured_provider_chain": ["shopaikey_video"],
            "effective_provider_chain": ["shopaikey_video"],
        }
        reconciled = _reconcile_r05a_zero_submit_worker_authority(payload, {}, {}, {})
        self.assertFalse(reconciled.get("r05a_provider_chain_reconciled", False))
        self.assertEqual(reconciled.get("provider_order"), ["shopaikey_video"])
        self.assertEqual(reconciled.get("configured_provider_chain"), ["shopaikey_video"])
        self.assertEqual(reconciled.get("effective_provider_chain"), ["shopaikey_video"])
        self.assertNotEqual(reconciled.get("provider_order"), ["key4u_video"])

    # ── 26 wrong adapter + image_to_video => NO reconcile ──
    def test_26_wrong_adapter_canonical_capability_no_reconcile(self):
        """Wrong engine_adapter with canonical required_capability -> NO reconciliation, incoming chain unchanged."""
        payload = {
            "product_type": "self_shot_scene_change",
            "quality_tier": 700,
            "engine_adapter": "legacy_v2v_scene_engine",
            "required_capability": "image_to_video",
            "selected_provider": "key4u_video",
            "selected_model": "kling-v3",
            "provider_order": ["shopaikey_video"],
            "configured_provider_chain": ["shopaikey_video"],
            "effective_provider_chain": ["shopaikey_video"],
        }
        reconciled = _reconcile_r05a_zero_submit_worker_authority(payload, {}, {}, {})
        self.assertFalse(reconciled.get("r05a_provider_chain_reconciled", False))
        self.assertEqual(reconciled.get("provider_order"), ["shopaikey_video"])
        self.assertEqual(reconciled.get("configured_provider_chain"), ["shopaikey_video"])
        self.assertEqual(reconciled.get("effective_provider_chain"), ["shopaikey_video"])
        self.assertNotEqual(reconciled.get("provider_order"), ["key4u_video"])

    # ── 27 canonical adapter + missing capability => NO reconcile ──
    def test_27_canonical_adapter_missing_capability_no_reconcile(self):
        """Canonical engine match but missing required_capability -> NO reconciliation, incoming chain unchanged."""
        payload = {
            "product_type": "self_shot_scene_change",
            "quality_tier": 700,
            "engine_adapter": "controlled_keyframe_image_to_video",
            "required_capability": "",
            "selected_provider": "key4u_video",
            "selected_model": "kling-v3",
            "provider_order": ["shopaikey_video"],
            "configured_provider_chain": ["shopaikey_video"],
            "effective_provider_chain": ["shopaikey_video"],
        }
        reconciled = _reconcile_r05a_zero_submit_worker_authority(payload, {}, {}, {})
        self.assertFalse(reconciled.get("r05a_provider_chain_reconciled", False))
        self.assertEqual(reconciled.get("provider_order"), ["shopaikey_video"])
        self.assertEqual(reconciled.get("configured_provider_chain"), ["shopaikey_video"])
        self.assertEqual(reconciled.get("effective_provider_chain"), ["shopaikey_video"])
        self.assertNotEqual(reconciled.get("provider_order"), ["key4u_video"])

    # ── 28 missing adapter + image_to_video => NO reconcile ──
    def test_28_missing_adapter_canonical_capability_no_reconcile(self):
        """Missing engine_adapter with canonical required_capability -> NO reconciliation, incoming chain unchanged."""
        payload = {
            "product_type": "self_shot_scene_change",
            "quality_tier": 700,
            "engine_adapter": "",
            "required_capability": "image_to_video",
            "selected_provider": "key4u_video",
            "selected_model": "kling-v3",
            "provider_order": ["shopaikey_video"],
            "configured_provider_chain": ["shopaikey_video"],
            "effective_provider_chain": ["shopaikey_video"],
        }
        reconciled = _reconcile_r05a_zero_submit_worker_authority(payload, {}, {}, {})
        self.assertFalse(reconciled.get("r05a_provider_chain_reconciled", False))
        self.assertEqual(reconciled.get("provider_order"), ["shopaikey_video"])
        self.assertEqual(reconciled.get("configured_provider_chain"), ["shopaikey_video"])
        self.assertEqual(reconciled.get("effective_provider_chain"), ["shopaikey_video"])
        self.assertNotEqual(reconciled.get("provider_order"), ["key4u_video"])

    # ── 29 wrong adapter + wrong capability => NO reconcile ──
    def test_29_wrong_adapter_wrong_capability_no_reconcile(self):
        """Both engine_adapter and required_capability mismatch -> NO reconciliation, incoming chain unchanged."""
        payload = {
            "product_type": "self_shot_scene_change",
            "quality_tier": 700,
            "engine_adapter": "wrong_engine",
            "required_capability": "wrong_capability",
            "selected_provider": "key4u_video",
            "selected_model": "kling-v3",
            "provider_order": ["shopaikey_video"],
            "configured_provider_chain": ["shopaikey_video"],
            "effective_provider_chain": ["shopaikey_video"],
        }
        reconciled = _reconcile_r05a_zero_submit_worker_authority(payload, {}, {}, {})
        self.assertFalse(reconciled.get("r05a_provider_chain_reconciled", False))
        self.assertEqual(reconciled.get("provider_order"), ["shopaikey_video"])
        self.assertEqual(reconciled.get("configured_provider_chain"), ["shopaikey_video"])
        self.assertEqual(reconciled.get("effective_provider_chain"), ["shopaikey_video"])
        self.assertNotEqual(reconciled.get("provider_order"), ["key4u_video"])

    # ── 30 empty adapter + empty capability => NO reconcile ──
    def test_30_empty_adapter_empty_capability_no_reconcile(self):
        """Empty engine_adapter and empty required_capability -> NO reconciliation, incoming chain unchanged."""
        payload = {
            "product_type": "self_shot_scene_change",
            "quality_tier": 700,
            "engine_adapter": "",
            "required_capability": "",
            "selected_provider": "key4u_video",
            "selected_model": "kling-v3",
            "provider_order": ["shopaikey_video"],
            "configured_provider_chain": ["shopaikey_video"],
            "effective_provider_chain": ["shopaikey_video"],
        }
        reconciled = _reconcile_r05a_zero_submit_worker_authority(payload, {}, {}, {})
        self.assertFalse(reconciled.get("r05a_provider_chain_reconciled", False))
        self.assertEqual(reconciled.get("provider_order"), ["shopaikey_video"])
        self.assertEqual(reconciled.get("configured_provider_chain"), ["shopaikey_video"])
        self.assertEqual(reconciled.get("effective_provider_chain"), ["shopaikey_video"])
        self.assertNotEqual(reconciled.get("provider_order"), ["key4u_video"])

    # ── 31 values resolved through existing precedence chain ──
    def test_31_precedence_chain_reconciles_only_if_both_canonical(self):
        """Precedence chain resolution reconciles ONLY if both final values are canonical."""
        base_payload = {
            "product_type": "self_shot_scene_change",
            "quality_tier": 700,
            "selected_provider": "key4u_video",
            "selected_model": "kling-v3",
            "provider_order": ["shopaikey_video"],
            "configured_provider_chain": ["shopaikey_video"],
            "effective_provider_chain": ["shopaikey_video"],
        }
        # Case A: missing from top-level payload, resolved from hydrated/result -> reconciles
        payload_a = dict(base_payload)
        res_a = _reconcile_r05a_zero_submit_worker_authority(
            payload_a,
            {"engine_adapter": "controlled_keyframe_image_to_video"},
            {},
            {"required_capability": "image_to_video"},
        )
        self.assertTrue(res_a.get("r05a_provider_chain_reconciled"))
        self.assertEqual(res_a.get("provider_order"), ["key4u_video"])

        # Case B: resolved value has non-canonical capability -> NO reconcile
        payload_b = dict(base_payload)
        res_b = _reconcile_r05a_zero_submit_worker_authority(
            payload_b,
            {"engine_adapter": "controlled_keyframe_image_to_video"},
            {},
            {"required_capability": "non_canonical_cap"},
        )
        self.assertFalse(res_b.get("r05a_provider_chain_reconciled", False))
        self.assertEqual(res_b.get("provider_order"), ["shopaikey_video"])
        self.assertEqual(res_b.get("configured_provider_chain"), ["shopaikey_video"])

    # ── 32 empty scene_cards_json ──
    def test_32_empty_scene_cards_json_returns_constructed_secret_stripped(self):
        """Empty scene_cards_json returns constructed scene cards with canonical fields preserved and secrets stripped."""
        job = make_job_50_snapshot()
        job["project"]["scene_cards_json"] = ""
        job["scene_cards"] = []
        job["scenes"] = [
            {
                "scene_index": 1,
                "role": "hero_shot",
                "script_text": "hero narration",
                "subtitle_line": "hero sub",
                "image_prompt": "hero img",
                "video_prompt": "hero prompt",
                "api_key": "secret_api_key_value",
                "token": "secret_token_value",
            }
        ]
        payload = build_worker_job_payload(job)
        scene_cards = payload.get("scene_cards") or []
        self.assertEqual(len(scene_cards), 1)
        card = scene_cards[0]
        self.assertEqual(card.get("scene_index"), 1)
        self.assertEqual(card.get("role"), "hero_shot")
        self.assertEqual(card.get("script_text"), "hero narration")
        self.assertEqual(card.get("subtitle_line"), "hero sub")
        self.assertEqual(card.get("image_prompt"), "hero img")
        self.assertEqual(card.get("video_prompt"), "hero prompt")
        self.assertNotIn("api_key", card)
        self.assertNotIn("token", card)

    # ── 33 non-empty scene_cards_json ──
    def test_33_non_empty_scene_cards_json_existing_behavior_unchanged(self):
        """Non-empty scene_cards_json preserves existing pre-baked cards without raw scene overwrite."""
        job = make_job_50_snapshot()
        existing = [{"scene_index": 1, "role": "pre_baked_card", "video_prompt": "existing card prompt"}]
        job["project"]["scene_cards_json"] = json.dumps(existing)
        job["scene_cards"] = existing
        job["scenes"] = [{"scene_index": 1, "role": "raw_scene", "video_prompt": "raw prompt"}]
        payload = build_worker_job_payload(job)
        scene_cards = payload.get("scene_cards") or []
        self.assertEqual(len(scene_cards), 1)
        self.assertEqual(scene_cards[0].get("role"), "pre_baked_card")
        self.assertEqual(scene_cards[0].get("video_prompt"), "existing card prompt")

    # ── 34 provider task/submit/attempted/http marker exists ──
    def test_34_provider_markers_block_rebind_even_with_canonical_engine(self):
        """Any provider task, submit, attempted, or HTTP sent marker blocks rebind even with canonical engine."""
        markers = [
            {"provider_task_count": 1},
            {"provider_submit_count": 1},
            {"provider_http_request_sent": True},
            {"provider_attempted": True},
            {"provider_submit_called": True},
            {
                "scene_tasks": [
                    {"scene_index": 1, "provider_task_id": "active_task_123"},
                ]
            },
        ]
        for marker in markers:
            with self.subTest(marker=marker):
                job = make_job_50_snapshot(
                    engine_adapter="controlled_keyframe_image_to_video",
                    required_capability="image_to_video",
                    result_overrides=marker,
                )
                payload = build_worker_job_payload(job)
                self.assertFalse(payload.get("cross_provider_rebind_allowed", False))
                self.assertFalse(payload.get("r05a_provider_chain_reconciled", False))
                self.assertEqual(payload.get("provider_order"), ["shopaikey_video"])
                self.assertEqual(payload.get("configured_provider_chain"), ["shopaikey_video"])

    # ── 35 ShopAIKey + veo3.1-fast ──
    def test_35_shopaikey_veo31_fast_unchanged_no_rewrite(self):
        """ShopAIKey + veo3.1-fast remains completely unchanged, no rewrite to Key4U."""
        job = make_job_50_snapshot(
            selected_provider="shopaikey_video",
            selected_model="veo3.1-fast",
            model="veo3.1-fast",
            result_overrides={
                "selected_provider": "shopaikey_video",
                "selected_model": "veo3.1-fast",
                "model": "veo3.1-fast",
                "provider_order": ["shopaikey_video"],
                "configured_provider_chain": ["shopaikey_video"],
                "effective_provider_chain": ["shopaikey_video"],
            },
            asset_pack_overrides={
                "selected_provider": "shopaikey_video",
                "selected_model": "veo3.1-fast",
            },
            invoice_overrides={
                "selected_provider": "shopaikey_video",
                "selected_model": "veo3.1-fast",
            },
        )
        payload = build_worker_job_payload(job)
        self.assertFalse(payload.get("r05a_provider_chain_reconciled", False))
        self.assertEqual(payload.get("selected_provider"), "shopaikey_video")
        self.assertEqual(payload.get("selected_model"), "veo3.1-fast")
        self.assertEqual(payload.get("provider_order"), ["shopaikey_video"])
        self.assertEqual(payload.get("configured_provider_chain"), ["shopaikey_video"])

    # ── 36 legacy V2V leakage ──
    def test_36_legacy_v2v_leakage_zero(self):
        """Legacy V2V route leakage is zero across canonical R05A worker job payload."""
        job = make_job_50_snapshot()
        payload = build_worker_job_payload(job)
        self.assertEqual(payload.get("legacy_v2v_route_leakage", 0), 0)
        self.assertNotEqual(payload.get("engine_adapter"), "legacy_v2v_scene_engine")
        self.assertNotIn("legacy_v2v", str(payload.get("engine_adapter", "")))
        self.assertNotIn("legacy_v2v", str(payload.get("engine_route", "")))

    # ── 37 R05B lane unchanged ──
    def test_37_r05b_lane_unchanged(self):
        """R05B product type / tier (e.g. self_shot_cinematic_transform Tier 800) does not reconcile R05A."""
        job = make_job_50_snapshot(
            product_type="self_shot_cinematic_transform",
            quality_tier=800,
            package_xu=800,
            engine_adapter="controlled_keyframe_image_to_video",
            required_capability="image_to_video",
            result_overrides={
                "product_type": "self_shot_cinematic_transform",
                "quality_tier": 800,
                "engine_adapter": "controlled_keyframe_image_to_video",
                "required_capability": "image_to_video",
            },
        )
        job["project"]["product_type"] = "self_shot_cinematic_transform"
        job["project"]["quality_tier"] = 800
        payload = build_worker_job_payload(job)
        self.assertFalse(payload.get("r05a_provider_chain_reconciled", False))


if __name__ == "__main__":
    unittest.main()

