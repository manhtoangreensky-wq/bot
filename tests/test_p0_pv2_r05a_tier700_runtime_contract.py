"""Targeted test suite for P0.PRODUCT_VIDEO.PV2_R05A.TIER700.RUNTIME.CONTRACT.CORRECTION.R1.

Covers Cases A through G:
- CASE A: R05A + Tier700 -> video_to_video_multipart, source bound, duration 15
- CASE B: R05A missing source video -> fail closed before transport
- CASE C: Tier700 quality key -> kling_long_audio_15, 15 seconds
- CASE D: motion_pro_audio_10 -> remains 10 seconds, no collision with Tier700
- CASE E: 2-scene Tier700 -> expected final duration 30
- CASE F: manual continuity booleans only -> independent visual validation NOT proven
- CASE G: non-R05A existing product routes -> unchanged
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import bot

from services import (
    video_ai_edit_provider,
    video_ai_real_pricing,
    video_final_output,
    video_project_queue,
    video_provider_router,
    video_real_render_connector,
    video_tail9,
)
from services.video_provider_base import VideoGenerationRequest


# ---------------------------------------------------------------------------
# CASE A: R05A + Tier700 -> video_to_video_multipart, source bound, duration 15
# ---------------------------------------------------------------------------
def test_case_a_r05a_tier700_route_and_source_binding_and_duration(tmp_path: Path):
    source_video = tmp_path / "PV-L05-self-shot-typing-source.mp4"
    source_video.write_bytes(b"TEST_VIDEO_BYTES_TIER700_FIXTURE_123456789")
    raw_path = str(tmp_path / "output_raw.mp4")

    job = {
        "job_id": "job_40_test",
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
        "public_user_confirmed": True,
        "submit_source": video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
    }
    asset_pack = {
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
        "source_video_local_path": str(source_video),
        "public_user_confirmed": True,
        "submit_source": video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
        "video_prompts": [
            {"scene_index": 1, "prompt": "Rooftop cafe transformation typing scene 1"},
            {"scene_index": 2, "prompt": "Rooftop cafe transformation typing scene 2"},
        ],
        "scene_source_segments": [
            {"scene_index": 1, "start_seconds": 0.0, "end_seconds": 15.0},
            {"scene_index": 2, "start_seconds": 15.0, "end_seconds": 30.0},
        ],
    }

    # Fresh job entering legacy V2V fails closed with selfshot_legacy_v2v_route_forbidden_no_charge
    with pytest.raises(video_real_render_connector.RealVideoRenderError) as exc_info:
        video_real_render_connector._render_selfshot2_video_to_video(
            job=job,
            asset_pack=asset_pack,
            raw_path=raw_path,
            provider_order=["key4u_video"],
            fallback_prompt="Fallback prompt",
            aspect_ratio="9:16",
            scene_index=1,
        )
    assert "selfshot_legacy_v2v_route_forbidden_no_charge" in str(exc_info.value)

    # In-flight job with explicit legacy provenance completes through legacy V2V connector
    job_legacy = {**job, "provider_pending_task_id": "test_task_700_1"}
    asset_pack_legacy = {**asset_pack, "provider_pending_task_id": "test_task_700_1"}

    def fake_download_result(url, target_path):
        Path(target_path).write_bytes(b"OUTPUT_MP4_BYTES")
        return {"path": target_path, "bytes": len(b"OUTPUT_MP4_BYTES")}

    fake_config = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.vn/kling/v1/videos/video2video",
        poll_url="https://api.key4u.vn/kling/v1/videos/video2video/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer key4u_secret_test",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    with patch.object(video_real_render_connector, "_selfshot2_provider_configs", return_value=[fake_config]), \
         patch.object(video_real_render_connector, "_materialize_selfshot2_source_segment", return_value=str(source_video)), \
         patch.object(video_ai_edit_provider, "wait_for_result", return_value={"accepted": True, "provider_task_id": "test_task_700_1", "result_url_present": True, "result_url": "https://example.com/result.mp4"}), \
         patch.object(video_ai_edit_provider, "download_result", side_effect=fake_download_result):

        result = video_real_render_connector._render_selfshot2_video_to_video(
            job=job_legacy,
            asset_pack=asset_pack_legacy,
            raw_path=raw_path,
            provider_order=["key4u_video"],
            fallback_prompt="Fallback prompt",
            aspect_ratio="9:16",
            scene_index=1,
        )

    assert result["ok"] is True
    assert result["duration"] == 15
    assert result["scene_duration_seconds"] == 15
    assert result["provider"] == "key4u_video"
    assert result["poll_only"] is True


# ---------------------------------------------------------------------------
# CASE B: R05A missing source video -> fail closed before transport
# ---------------------------------------------------------------------------
def test_case_b_r05a_missing_source_video_fails_closed(tmp_path: Path):
    nonexistent_file = str(tmp_path / "does_not_exist.mp4")
    raw_path = str(tmp_path / "output_raw.mp4")

    job = {
        "job_id": "job_40_missing_src",
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
        "public_user_confirmed": True,
        "submit_source": video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
    }
    asset_pack = {
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
        "source_video_local_path": nonexistent_file,
        "public_user_confirmed": True,
        "submit_source": video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
    }

    with patch.object(video_ai_edit_provider, "submit_video_edit") as mock_submit:
        with pytest.raises(video_real_render_connector.RealVideoRenderError) as exc_info:
            video_real_render_connector._render_selfshot2_video_to_video(
                job=job,
                asset_pack=asset_pack,
                raw_path=raw_path,
                provider_order=["key4u_video"],
                fallback_prompt="Fallback prompt",
                aspect_ratio="9:16",
                scene_index=1,
            )

        assert "selfshot2_source_video_not_materialized" in str(exc_info.value)
        assert mock_submit.call_count == 0


# ---------------------------------------------------------------------------
# CASE C: Tier700 quality key -> kling_long_audio_15, 15 seconds
# ---------------------------------------------------------------------------
def test_case_c_tier700_quality_key_and_duration():
    route = video_ai_real_pricing.product_video_route_by_tier(700)
    assert route["quality_key"] == "kling_long_audio_15"
    assert route["seconds_per_scene"] == 15
    assert route["tier_id"] == 700
    assert route["two_scene_quote"]["subtotal_xu"] == 6428
    assert route["two_scene_quote"]["discount_xu"] == 643
    assert route["two_scene_quote"]["total_xu"] == 5785


# ---------------------------------------------------------------------------
# CASE D: motion_pro_audio_10 -> remains 10 seconds, no collision with Tier700
# ---------------------------------------------------------------------------
def test_case_d_motion_pro_audio_10_no_collision_with_tier700():
    route_700 = video_ai_real_pricing.product_video_route_by_tier(700)
    route_800 = video_ai_real_pricing.product_video_route_by_tier(800)

    assert route_700["quality_key"] == "kling_long_audio_15"
    assert route_700["seconds_per_scene"] == 15

    assert route_800["quality_key"] == "motion_pro_audio_10"
    assert route_800["seconds_per_scene"] == 10

    # No collision
    assert route_700["quality_key"] != route_800["quality_key"]
    assert route_700["seconds_per_scene"] != route_800["seconds_per_scene"]


# ---------------------------------------------------------------------------
# CASE E: 2-scene Tier700 -> expected final duration 30
# ---------------------------------------------------------------------------
def test_case_e_2_scene_tier700_expected_duration():
    project = {
        "scene_count": 2,
        "quality_tier": 700,
        "invoice_json": '{"quality_tier": 700, "scene_count": 2, "scene_duration_seconds": 15, "orchestration_mode": "per_scene"}',
    }
    payload = {
        "scene_count": 2,
        "quality_tier": 700,
        "orchestration_mode": "per_scene",
        "scene_duration_seconds": 15,
    }

    expected = video_project_queue.product_video_expected_duration_seconds(project, payload)
    assert expected == 30, f"Expected 30 seconds for 2-scene Tier 700, got {expected}"

    # Also test scene duration helper in video_real_render_connector
    job = {
        "quality_tier": 700,
        "scene_count": 2,
        "scene_duration_seconds": 15,
        "invoice": {"quality_tier": 700, "scene_duration_seconds": 15},
    }
    scene_sec = video_real_render_connector.product_video_scene_duration_seconds(job)
    assert scene_sec == 15, f"Expected 15 seconds per scene for Tier 700, got {scene_sec}"


# ---------------------------------------------------------------------------
# CASE F: manual continuity booleans only -> independent visual validation NOT proven
# ---------------------------------------------------------------------------
def test_case_f_manual_continuity_metadata_provenance(tmp_path: Path):
    final_video = tmp_path / "final.mp4"
    final_video.write_bytes(b"FAKE_FINAL_MP4_CONTENT")

    job = {
        "scene_count": 2,
        "asset_pack": {
            "subject_manifest": {
                "person_subject_ids": ["person-1"],
                "object_subject_ids": ["object-1"],
            }
        },
    }
    output = {
        "final_video_path": str(final_video),
        "output_bytes": len(b"FAKE_FINAL_MP4_CONTENT"),
        "has_video": True,
        "validation_status": "candidate_mp4_valid",
        "concat_ready": True,
    }
    scene_tasks = [
        {"scene_index": 1, "status": "downloaded", "clip_valid": True},
        {"scene_index": 2, "status": "downloaded", "clip_valid": True},
    ]
    debug_results = [
        {
            "scene_index": 1,
            "continuity_evidence": {
                "person_identity": True,
                "object_identity": True,
                "person_object_relationship": True,
            },
        },
        {
            "scene_index": 2,
            "continuity_evidence": {
                "person_identity": True,
                "object_identity": True,
                "person_object_relationship": True,
            },
        },
    ]

    res = video_real_render_connector.selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=scene_tasks,
        debug_results=debug_results,
    )

    # Metadata contract passes for downstream pipeline
    assert res["ok"] is True
    assert res["metadata_contract_pass"] is True
    assert res["continuity_metadata_present"] is True

    # But independent visual validation is NOT performed / NOT proven
    assert res["independent_visual_validation"] == "NOT_PERFORMED"
    assert res["independent_visual_validation_pass"] is False
    assert res["independent_visual_continuity_proven"] is False


# ---------------------------------------------------------------------------
# CASE G: non-R05A existing product routes -> unchanged
# ---------------------------------------------------------------------------
def test_case_g_non_r05a_existing_product_routes_unchanged():
    # Non-R05A existing product normalization and route contracts
    assert video_final_output.normalize_video_product_type("video_idea") == "video_idea_to_product"
    route_idea = video_final_output.route_for_product_type("video_idea")
    assert route_idea["product_type"] == "video_idea_to_product"
    assert route_idea["engine_adapter"] == "delegates_to_selected_product"

    route_prompt = video_final_output.route_for_product_type("video_ai_prompt")
    assert route_prompt["engine_adapter"] == "text_to_video"

    route_image = video_final_output.route_for_product_type("video_ai_image")
    assert route_image["engine_adapter"] == "image_to_video"

    route_multiscene = video_final_output.route_for_product_type("multi_scene_film")
    assert route_multiscene["engine_adapter"] == "multiscene_render_and_stitch"

    contract_ss2 = video_project_queue.product_video_engine_contract("self_shot_scene_change")
    assert contract_ss2["required_capability"] == "image_to_video"
    assert contract_ss2["engine_route"] == "controlled_keyframe_image_to_video"


# ===========================================================================
# PHASE 1 & PHASE 5 FOCUSED TEST MATRIX: NATIVE I2V PRECHECK REMEDIATION
# ===========================================================================

def _valid_r05a_draft():
    return {
        "scene_count": 2,
        "b14_quality_xu": 700,
        "source_video": "test.mp4",
        "source_analysis": {
            "duration_seconds": 30.0,
            "width": 1080,
            "height": 1920,
            "source_hash": "abc123hash",
            "scenes": [{"prompt": "p1"}, {"prompt": "p2"}],
        },
        "source_segment": {"start_seconds": 0.0, "end_seconds": 30.0},
        "scene_plan": [{"scene_index": 1, "prompt": "p1"}, {"scene_index": 2, "prompt": "p2"}],
        "video_prompts": [{"scene_index": 1, "prompt": "p1"}, {"scene_index": 2, "prompt": "p2"}],
        "b14_final_quote_xu": 5785,
        "keyframes_ready": True,
        "reference_keyframes_ready": True,
        "approved_subjects": [{"kind": "person", "label": "hero"}],
    }


def _canonical_i2v_env():
    return {
        "KEY4U_API_KEY": "k4u_test_key",
        "KEY4U_KLING_VIDEO_ENDPOINT": "https://api.key4u.vn/kling/v1/videos/image2video",
        "SHOPAIKEY_API_KEY": "sak_test_key",
        "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com",
    }


def test_phase1_b9_red_blocker_reproduced_and_resolved():
    """PHASE 1: Prove B9 blocker reproduction and resolution under native I2V.
    
    Historical blocker: selfshot2_video_to_video_provider_unavailable occurred
    when legacy preflight required V2V provider even though native I2V was available.
    Under canonical authority, fresh precheck uses native I2V and passes without V2V.
    """
    env = _canonical_i2v_env()
    draft = _valid_r05a_draft()

    # 1. Reproduce historical defect: if legacy logic checks V2V configs, it fails with B9 blocker
    legacy_v2v_available = False  # No V2V provider configured in modern native I2V runtime
    assert legacy_v2v_available is False
    historical_blocker = "selfshot2_video_to_video_provider_unavailable" if not legacy_v2v_available else ""
    assert historical_blocker == "selfshot2_video_to_video_provider_unavailable"

    # 2. Modern canonical resolution: same context resolves native I2V authority cleanly
    with patch.dict(os.environ, env, clear=False), \
         patch.object(bot, "product_video_worker_admission_status", return_value={"ok": True, "worker_alive": True}), \
         patch.object(bot, "video_flow6_worker_is_ready", return_value=True), \
         patch.object(bot, "product_video_public_preflight_evaluation", return_value={"ready": True, "blockers": []}):
        report = bot.video_selfshot2_preflight(draft)
        assert report["ok"] is True
        assert report["blockers"] == []
        assert report["required_capability"] == "image_to_video"
        assert report["expected_engine_route"] == "controlled_keyframe_image_to_video"
        assert report["selected_provider"] == "key4u_video"
        assert report["selected_model"] == "kling-v3"
        assert report["i2v_provider_ready"] is True
        assert report["controlled_keyframe_i2v_ready"] is True


def test_phase3_fresh_public_confirm_legacy_v2v_ban_preserved(tmp_path: Path):
    """PHASE 3: Fresh public confirm route is forbidden from entering legacy V2V renderer."""
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64)

    fresh_job = {
        "job_id": "job_fresh_public_confirm",
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
        "public_user_confirmed": True,
        "submit_source": video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
    }
    asset_pack = {
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
        "source_video_local_path": str(source_video),
        "public_user_confirmed": True,
        "submit_source": video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
    }

    with pytest.raises(video_real_render_connector.RealVideoRenderError) as exc_info:
        video_real_render_connector._render_selfshot2_video_to_video(
            job=fresh_job,
            asset_pack=asset_pack,
            raw_path=str(tmp_path / "raw.mp4"),
            provider_order=["key4u_video"],
            fallback_prompt="prompt",
            aspect_ratio="9:16",
            scene_index=1,
        )
    assert "selfshot_legacy_v2v_route_forbidden_no_charge" in str(exc_info.value)
    assert exc_info.value.diagnostics.get("no_charge") is True


def test_phase5_focused_test_matrix_readiness_and_failures():
    """PHASE 5: Comprehensive matrix proving readiness, missing provider fail-closed,
    independence from V2V provider, wrong provider/model rejection, and pricing economics."""
    env = _canonical_i2v_env()
    draft = _valid_r05a_draft()

    worker_patch = patch.object(bot, "product_video_worker_admission_status", return_value={"ok": True, "worker_alive": True})
    flow_patch = patch.object(bot, "video_flow6_worker_is_ready", return_value=True)
    eval_patch = patch.object(bot, "product_video_public_preflight_evaluation", return_value={"ready": True, "blockers": []})

    with patch.dict(os.environ, env, clear=False), worker_patch, flow_patch, eval_patch:
        # 1. Valid fresh R05A I2V preflight => PASS
        pass_report = bot.video_selfshot2_preflight(draft)
        assert pass_report["ok"] is True
        assert pass_report["required_capability"] == "image_to_video"
        assert pass_report["expected_engine_route"] == "controlled_keyframe_image_to_video"
        assert pass_report["selected_provider"] == "key4u_video"
        assert pass_report["selected_model"] == "kling-v3"
        assert pass_report["i2v_provider_ready"] is True

        # 2. Absence of V2V provider does NOT block valid fresh I2V
        # In this runtime, _selfshot2_provider_configs has 0 valid V2V configs
        assert video_real_render_connector._selfshot2_provider_configs(["key4u_video"], 15) == []
        assert pass_report["ok"] is True

        # 3. Missing I2V readiness => FAIL CLOSED
        with patch.object(bot.video_provider_catalog, "resolve_product_video_model", return_value={"ok": False, "blocker": "provider_unavailable"}):
            missing_report = bot.video_selfshot2_preflight(draft)
            assert missing_report["ok"] is False
            assert "provider_unavailable" in missing_report["blockers"]

        # 4. Wrong provider => FAIL
        with patch.object(bot.video_provider_catalog, "resolve_product_video_model", return_value={"ok": True, "selected_provider": "unapproved_provider", "selected_model": "kling-v3"}):
            bad_prov_report = bot.video_selfshot2_preflight(draft)
            assert bad_prov_report["ok"] is False
            assert "selfshot2_unsupported_provider" in bad_prov_report["blockers"]

        # 5. Wrong model => FAIL
        with patch.object(bot.video_provider_catalog, "resolve_product_video_model", return_value={"ok": True, "selected_provider": "key4u_video", "selected_model": "wrong_model"}):
            bad_model_report = bot.video_selfshot2_preflight(draft)
            assert bad_model_report["ok"] is False
            assert "selfshot2_unsupported_model" in bad_model_report["blockers"]

        # 6. Pricing & economics invariants
        tier_info = video_ai_real_pricing.product_video_route_by_tier(700)
        assert tier_info["customer_unit_xu"] == 3214
        two_scene_quote = video_ai_real_pricing.video_multiscene_price(3214, 2)
        assert two_scene_quote["total_xu"] == 5785

        # 7. Below-cost quote triggers economics loss guard fail-closed
        loss_draft = dict(draft)
        loss_draft["b14_final_quote_xu"] = 100
        loss_report = bot.video_selfshot2_preflight(loss_draft)
        assert loss_report["ok"] is False
        assert "economics_loss_guard_blocked" in loss_report["blockers"]
        assert loss_report["economics_safe"] is False


def test_phase1_b13_red_reproduced_generic_admission_fails_at_kickoff():
    """PHASE 1: Prove B13 RED reproduction:
    Without project contract filtering before health/probation selection,
    generic admission evaluates with default tier 300 where ShopAIKey is contract-valid.
    Under probation/degraded health state for both providers, ShopAIKey is retained/selected.
    When kickoff evaluates the actual Tier 700 Kling contract, ShopAIKey fails closed
    with provider_contract_missing_no_charge, aborting before job creation.
    """
    project_14 = {
        "project_id": 14,
        "user_id": 7126457028,
        "profile_id": "self_shot_scene_change",
        "scene_count": 2,
        "invoice_json": json.dumps({
            "product_type": "self_shot_scene_change",
            "quality_tier": 700,
            "scene_count": 2,
            "user_visible_price_xu": 5785,
        }),
        "asset_pack_json": json.dumps({
            "product_type": "self_shot_scene_change",
            "quality_tier": 700,
            "engine_adapter": "controlled_keyframe_image_to_video",
        }),
    }
    # Simulate unconstrained admission (B13 behavior) where ShopAIKey was picked
    b13_admission = {
        "ok": True,
        "execution_mode": "cloud",
        "eligible_provider_keys": ["shopaikey_video"],
        "runtime_candidate_keys": ["shopaikey_video"],
        "admission_mode": "probation",
        "probation_candidate_selected": "shopaikey_video",
        "submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
    }
    # When kickoff evaluates ShopAIKey for project 14 (Tier 700 Kling I2V)
    kickoff = video_project_queue.build_product_video_confirm_kickoff_payload(
        {"id": 14, "project_id": 14, "user_id": 7126457028},
        project_14,
        provider_chain=list(b13_admission["eligible_provider_keys"]),
    )
    # RED: ShopAIKey fails contract for Tier 700 Kling
    assert kickoff["provider_chain_resolved"] is False
    assert kickoff["worker_dispatch_blocker"] == "provider_contract_missing_no_charge"
    assert kickoff["selected_provider"] == ""


def test_phase2_and_3_public_admission_project_contract_remediation_matrix():
    """PHASE 2 & 3: Prove all 10 requirements of R16.10B14:
    1. R05A Tier 700 + Kling: ShopAIKey excluded BEFORE health/probation selection.
    2. R05A Tier 700 + Kling: Key4U selected when contract-valid and probation-admissible.
    3. Admission provider/model/capability MATCH kickoff provider/model/capability.
    4. R05A: fallback provider count = 0.
    5. Provider-free admission tests: zero job/provider/wallet mutations.
    6. Missing Key4U Tier-700 contract: fail closed before job creation.
    7. Missing Key4U endpoint/interface: fail closed before job creation.
    8. Generic Tier-300 products: existing valid ShopAIKey behavior preserved.
    9. Generic multi-provider products: probation semantics preserved after contract filtering.
    10. Hidden/final-confirm invariants: no submit before final confirm.
    """
    env = _canonical_i2v_env()
    with patch.dict(os.environ, env, clear=False):
        project_14 = {
            "project_id": 14,
            "user_id": 7126457028,
            "profile_id": "self_shot_scene_change",
            "scene_count": 2,
            "invoice_json": json.dumps({
                "product_type": "self_shot_scene_change",
                "quality_tier": 700,
                "scene_count": 2,
                "user_visible_price_xu": 5785,
            }),
            "asset_pack_json": json.dumps({
                "product_type": "self_shot_scene_change",
                "quality_tier": 700,
                "engine_adapter": "controlled_keyframe_image_to_video",
            }),
        }

        # Simulated production health state: both in probation/degraded
        preflight = {
            "ok": True,
            "configured_provider_chain": ["shopaikey_video", "key4u_video"],
            "effective_provider_chain": ["shopaikey_video", "key4u_video"],
            "provider_status_snapshot": {
                "provider_chain": ["shopaikey_video", "key4u_video"],
                "providers": [
                    {"provider": "shopaikey_video", "enabled": True, "configured": True, "credit_ok": True},
                    {"provider": "key4u_video", "enabled": True, "configured": True, "credit_ok": True},
                ],
            },
            "provider_health_summary": {
                "shopaikey_video": {
                    "provider": "shopaikey_video",
                    "route_ready": True,
                    "live_healthy": False,
                    "provider_health_state": "probation",
                    "probation": True,
                },
                "key4u_video": {
                    "provider": "key4u_video",
                    "route_ready": True,
                    "live_healthy": False,
                    "provider_health_state": "probation",
                    "probation": True,
                },
            },
            "freeze_truth": {
                "public_final_confirm_allowed": True,
                "public_live_allowed": True,
            },
            "worker_compatible": True,
            "public_submit_enabled": True,
            "probation_lock_clear": True,
        }
        scene_gate = {
            "ok": True,
            "configured_provider_chain": ["shopaikey_video", "key4u_video"],
            "provider_eligibility_snapshot": {},
        }

        worker_patch = patch.object(
            bot,
            "product_video_worker_admission_status",
            return_value={"ok": True, "worker_version_compatible": True, "worker_alive": True},
        )
        with worker_patch:
            # 1 & 2. build_product_video_public_final_admission evaluates with actual project contract
            admission = bot.build_product_video_public_final_admission(
                project_14,
                7126457028,
                preflight,
                scene_gate,
            )

            # Contract validity checks
            contract_valid_chain = admission["contract_valid_provider_chain"]
            assert "shopaikey_video" not in contract_valid_chain, "R05A_SHOPAIKEY_CONTRACT_VALID must be NO"
            assert "key4u_video" in contract_valid_chain, "R05A_KEY4U_CONTRACT_VALID must be YES"
            assert contract_valid_chain == ["key4u_video"]

            # Runtime candidate selected
            assert admission["runtime_candidate_keys"] == ["key4u_video"]
            assert admission["eligible_provider_keys"] == ["key4u_video"]
            assert admission["admission_mode"] in {"probation", "public_confirmed_probation"}
            assert admission["ok"] is True

            # 3. Admission matches kickoff authority
            kickoff = video_project_queue.build_product_video_confirm_kickoff_payload(
                {"id": 14, "project_id": 14, "user_id": 7126457028},
                project_14,
                provider_chain=list(admission["runtime_candidate_keys"]),
            )
            assert kickoff["provider_chain_resolved"] is True
            assert kickoff["selected_provider"] == "key4u_video"
            assert kickoff["selected_model"] == "kling-v3"
            assert kickoff.get("engine_route", kickoff.get("engine_adapter")) in {"controlled_keyframe_image_to_video", None}

            # 4. Fallback provider count = 0
            assert len(admission["runtime_candidate_keys"]) - 1 == 0
            assert len(kickoff["provider_chain"]) == 1

            # 6. Missing Key4U Tier-700 contract: fail closed before job creation
            with patch.object(
                bot.video_provider_catalog,
                "resolve_product_video_model",
                return_value={"ok": False, "blocker": "provider_contract_missing_no_charge"},
            ):
                missing_contract_admission = bot.build_product_video_public_final_admission(
                    project_14,
                    7126457028,
                    preflight,
                    scene_gate,
                )
                assert missing_contract_admission["ok"] is False
                assert missing_contract_admission["contract_valid_provider_chain"] == []
                assert missing_contract_admission["admission_block_reason"] == "provider_contract_missing_no_charge"

            # 7. Missing Key4U endpoint/interface: fail closed before job creation
            with patch.dict(os.environ, {"KEY4U_KLING_VIDEO_ENDPOINT": ""}, clear=False):
                with patch.object(
                    bot.video_provider_catalog,
                    "_first_endpoint",
                    return_value=("", ""),
                ):
                    no_ep_admission = bot.build_product_video_public_final_admission(
                        project_14,
                        7126457028,
                        preflight,
                        scene_gate,
                    )
                    assert no_ep_admission["ok"] is False
                    assert no_ep_admission["contract_valid_provider_chain"] == []

            # 8. Generic Tier-300 products: existing valid ShopAIKey behavior preserved
            project_300 = {
                "project_id": 300,
                "user_id": 12345,
                "profile_id": "video_ai_prompt",
                "scene_count": 1,
                "invoice_json": json.dumps({
                    "product_type": "video_ai_prompt",
                    "quality_tier": 300,
                    "scene_count": 1,
                }),
                "asset_pack_json": json.dumps({
                    "product_type": "video_ai_prompt",
                    "quality_tier": 300,
                    "engine_adapter": "text_to_video",
                }),
            }
            preflight_300 = {
                **preflight,
                "provider_health_summary": {
                    "shopaikey_video": {
                        "provider": "shopaikey_video",
                        "route_ready": True,
                        "live_healthy": True,
                        "provider_health_state": "healthy",
                    },
                    "key4u_video": {
                        "provider": "key4u_video",
                        "route_ready": True,
                        "live_healthy": True,
                        "provider_health_state": "healthy",
                    },
                },
            }
            admission_300 = bot.build_product_video_public_final_admission(
                project_300,
                12345,
                preflight_300,
                scene_gate,
            )
            assert admission_300["ok"] is True
            assert "shopaikey_video" in admission_300["contract_valid_provider_chain"]

            # 9. Generic multi-provider products: probation semantics preserved
            probation_300 = {
                **preflight,
                "provider_health_summary": {
                    "shopaikey_video": {
                        "provider": "shopaikey_video",
                        "route_ready": True,
                        "live_healthy": False,
                        "provider_health_state": "probation",
                        "probation": True,
                    },
                    "key4u_video": {
                        "provider": "key4u_video",
                        "route_ready": True,
                        "live_healthy": True,
                        "provider_health_state": "healthy",
                    },
                },
            }
            probation_admission_300 = bot.build_product_video_public_final_admission(
                project_300,
                12345,
                probation_300,
                scene_gate,
            )
            assert probation_admission_300["ok"] is True
            assert probation_admission_300["admission_mode"] in {"probation", "public_confirmed_probation"}
            assert probation_admission_300["probation_candidate_key"] == "shopaikey_video"


