"""Tests for P0.PRODUCT_VIDEO_STORYBOARD_DUAL_TIER_ROUTING.

Verifies the Owner-approved dual-tier routing architecture for Storyboard (Direction A):
1. Option B (Standard / Budget / Fast / Tier 400):
   - Routes to shopaikey_video with veo3.1-fast ($0.70/scene, $1.40 for 2 scenes).
   - Customer unit: 371 Xu/scene, 2-scene quote: 668 Xu.
   - Scene duration: 8 seconds per scene.
2. Option A (Pro / High Quality / Studio / Tier 800 - Storyboard 8s):
   - Routes to key4u_video with kling-v3 ($12.24009792/scene, $24.48019584 for 2 scenes).
   - Customer unit: 1,714 Xu/scene, 2-scene quote: 3,086 Xu.
   - Scene duration: 8 seconds per scene.
3. Strict Tier Eligibility & Supreme Precedence:
   - Storyboard public catalog and package resolutions strictly restricted to [400, 800].
   - All other tiers (200, 300, 500, 600, 700, 1000, 1200, 1500) FAIL CLOSED before provider,
     even when selected_provider, selected_model, asset_pack, or invoice overrides are supplied.
   - Cross-tier overrides (e.g. Tier 400 with Kling or Key4U; Tier 800 with Veo or ShopAIKey) are BLOCKED.
4. Production Spend Authority (services/provider_spend_guard.py):
   - Tier 400 2 scenes: 1,400,000 micro-USD ($1.40).
   - Tier 800 2 scenes: 24,480,196 micro-USD ($24.48019584).
   - Strict validation: wrong provider, model, tier, duration fail-closed.
   - Caller metadata cannot elevate canonical spend bounds.
5. Zero real external provider calls; all provider I/O mocked and test-isolated.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys

# Ensure optional external heavy packages don't break import of bot if not installed
for _m in (
    "google",
    "google.genai",
    "google.genai.types",
    "openai",
    "uvicorn",
    "numpy",
    "onnxruntime",
    "cv2",
    "PIL",
    "PIL.Image",
    "av",
    "faster_whisper",
    "ctranslate2",
    "edge_tts",
    "yt_dlp",
    "paramiko",
    "docx",
    "fitz",
    "pypdf",
    "multipart",
    "multipart.multipart",
):
    if _m not in sys.modules:
        try:
            __import__(_m)
        except ImportError:
            from unittest.mock import MagicMock
            sys.modules[_m] = MagicMock()

import pytest

import bot
from services import provider_spend_guard as psg
from services import remote_worker_api
from tests.test_p0_paid_spend_guard_and_bot_origin import (
    _create_owner_live_authorization_test_fixture,
    create_test_mint_authority,
    create_bot_confirmation,
    PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
    BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED,
)
from services import video_tail9
from services import video_uifreeze1
from services import video_real_render_connector
from services.video_real_render_connector import (
    RealVideoRenderError,
    STORYBOARD_PROVEN_I2V_MODELS,
    STORYBOARD_PROVEN_I2V_MODELS_BY_PROVIDER,
    STORYBOARD_DEFAULT_I2V_MODEL_BY_PROVIDER,
    _provider_order,
    _resolve_storyboard_i2v_model,
    render_real_video_job,
)


@pytest.fixture
def sample_panels(tmp_path):
    p1 = tmp_path / "panel_01.png"
    p2 = tmp_path / "panel_02.png"
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    p1.write_bytes(png_bytes)
    p2.write_bytes(png_bytes)
    return str(p1), str(p2)


def _build_storyboard_job(panel1: str, panel2: str, *, tier_id: int, job_id: int = 1180, project_id: int = 2180) -> dict:
    cards = [
        {
            "scene_index": 1,
            "card_index": 1,
            "scene_id": "scene_1",
            "image_path": panel1,
            "raw_image_path": panel1,
            "prompt": "Modern coffee shop morning scene, gentle camera pan",
        },
        {
            "scene_index": 2,
            "card_index": 2,
            "scene_id": "scene_2",
            "image_path": panel2,
            "raw_image_path": panel2,
            "prompt": "Barista pouring latte art into cup, warm golden lighting",
        },
    ]
    return {
        "id": job_id,
        "job_id": job_id,
        "project_id": project_id,
        "source": "product_video",
        "product_video": True,
        "provider_submit_allowed": True,
        "product_type": "storyboard_to_video",
        "orchestration_mode": "per_scene_8s",
        "scene_count": 2,
        "aspect_ratio": "9:16",
        "tier_id": tier_id,
        "scene_cards": cards,
        "storyboard_panels": cards,
        "storyboard_cards": cards,
        "scenes": cards,
        "engine_adapter": "storyboard_scene_image_video_engine",
        "engine_route": "storyboard_to_video",
        "asset_pack": {
            "product_type": "storyboard_prompt",
            "aspect_ratio": "9:16",
            "tier_id": tier_id,
            "orchestration_mode": "per_scene_8s",
            "scene_cards": cards,
        },
        "invoice": {
            "tier_id": tier_id,
            "quality_xu": tier_id,
            "scene_count": 2,
            "scene_duration_seconds": 8,
        },
    }


class TestStoryboardTierEligibilityAndFailClosed:
    """Proves Storyboard public catalog and router are strictly locked to [400, 800] and fail-closed for other tiers."""

    def test_storyboard_commercial_contract_limits_tiers_to_400_and_800(self):
        contract = video_tail9.commercial_contract("storyboard_prompt")
        assert contract["supported_quality_tiers"] == (400, 800)
        assert contract["scene_duration_seconds"] == 8

    def test_storyboard_catalog_report_returns_strictly_400_and_800(self):
        report = video_uifreeze1.catalog_report(
            "storyboard_prompt",
            scene_count=2,
            ratio="9:16",
            required_capability="image_to_video",
        )
        assert report["ok"] is True
        assert report["tier_ids"] == [400, 800]
        offers = report["offers"]
        assert len(offers) == 2

        # Tier 400 offer
        o400 = next(o for o in offers if o["tier_id"] == 400)
        assert o400["unit_xu"] == 371
        assert o400["seconds"] == 8

        # Tier 800 offer (Storyboard 8s specific pricing)
        o800 = next(o for o in offers if o["tier_id"] == 800)
        assert o800["unit_xu"] == 1714
        assert o800["seconds"] == 8
        assert "8s" in o800["name"]

    def test_storyboard2_package_resolutions_returns_strictly_400_and_800(self):
        state = {
            "flow_kind": "storyboard",
            "scene_count": 2,
            "ratio": "9:16",
        }
        packages = bot.storyboard2_package_resolutions(state)
        prices = [p["price"] for p in packages]
        assert prices == [400, 800]

    def test_unsupported_tier_no_override_blocks(self):
        unsupported = [200, 300, 401, 500, 600, 700, 799, 801, 999, 1000, 1200, 1500]
        for tid in unsupported:
            job = {
                "product_type": "storyboard_to_video",
                "tier_id": tid,
            }
            with pytest.raises(RealVideoRenderError) as exc_info:
                _provider_order(job)
            assert f"storyboard_unsupported_tier:{tid}" in str(exc_info.value)

            with pytest.raises(RealVideoRenderError) as exc_info2:
                _resolve_storyboard_i2v_model(job)
            assert f"storyboard_unsupported_tier:{tid}" in str(exc_info2.value)

    def test_unsupported_tier_provider_override_blocks(self):
        """Unsupported tier must block even if valid provider is explicitly requested."""
        for tid in [401, 500, 700, 799, 801, 999]:
            job_key4u = {
                "product_type": "storyboard_to_video",
                "tier_id": tid,
                "selected_provider": "key4u_video",
            }
            with pytest.raises(RealVideoRenderError) as exc:
                _provider_order(job_key4u)
            assert f"storyboard_unsupported_tier:{tid}" in str(exc.value)

            job_shopai = {
                "product_type": "storyboard_to_video",
                "tier_id": tid,
                "selected_provider": "shopaikey_video",
            }
            with pytest.raises(RealVideoRenderError) as exc:
                _provider_order(job_shopai)
            assert f"storyboard_unsupported_tier:{tid}" in str(exc.value)

    def test_unsupported_tier_model_override_blocks(self):
        """Unsupported tier must block even if valid model is explicitly requested."""
        for tid in [401, 500, 700, 799, 801, 999]:
            job_kling = {
                "product_type": "storyboard_to_video",
                "tier_id": tid,
                "selected_model": "kling-v3",
            }
            with pytest.raises(RealVideoRenderError) as exc:
                _provider_order(job_kling)
            assert f"storyboard_unsupported_tier:{tid}" in str(exc.value)

            with pytest.raises(RealVideoRenderError) as exc:
                _resolve_storyboard_i2v_model(job_kling)
            assert f"storyboard_unsupported_tier:{tid}" in str(exc.value)

            job_veo = {
                "product_type": "storyboard_to_video",
                "tier_id": tid,
                "selected_model": "veo3.1-fast",
            }
            with pytest.raises(RealVideoRenderError) as exc:
                _provider_order(job_veo)
            assert f"storyboard_unsupported_tier:{tid}" in str(exc.value)

            with pytest.raises(RealVideoRenderError) as exc:
                _resolve_storyboard_i2v_model(job_veo)
            assert f"storyboard_unsupported_tier:{tid}" in str(exc.value)

    def test_unsupported_tier_asset_pack_and_invoice_overrides_block(self):
        """Unsupported tier inside asset_pack or invoice must fail closed for any unsupported tier."""
        for tid in [401, 500, 700, 799, 801, 999]:
            job_asset = {
                "product_type": "storyboard_to_video",
                "asset_pack": {
                    "tier_id": tid,
                    "selected_provider": "key4u_video",
                    "selected_model": "kling-v3",
                },
            }
            with pytest.raises(RealVideoRenderError) as exc:
                _provider_order(job_asset)
            assert f"storyboard_unsupported_tier:{tid}" in str(exc.value)

            job_inv = {
                "product_type": "storyboard_to_video",
                "invoice": {
                    "tier_id": tid,
                    "selected_provider": "shopaikey_video",
                    "selected_model": "veo3.1-fast",
                },
            }
            with pytest.raises(RealVideoRenderError) as exc:
                _provider_order(job_inv)
            assert f"storyboard_unsupported_tier:{tid}" in str(exc.value)

    def test_cross_tier_overrides_block(self):
        """Cross-tier provider or model overrides must be strictly blocked."""
        # Tier 400 with Key4U or Kling -> BLOCK
        job_t400_k4u = {
            "product_type": "storyboard_to_video",
            "tier_id": 400,
            "selected_provider": "key4u_video",
        }
        with pytest.raises(RealVideoRenderError) as exc:
            _provider_order(job_t400_k4u)
        assert "storyboard_cross_tier_override:400:key4u_video" in str(exc.value)

        job_t400_kling = {
            "product_type": "storyboard_to_video",
            "tier_id": 400,
            "selected_model": "kling-v3",
        }
        with pytest.raises(RealVideoRenderError) as exc:
            _provider_order(job_t400_kling)
        assert "storyboard_cross_tier_override:400:kling-v3" in str(exc.value)

        with pytest.raises(RealVideoRenderError) as exc:
            _resolve_storyboard_i2v_model(job_t400_kling)
        assert "storyboard_cross_tier_override:400:kling-v3" in str(exc.value)

        # Tier 800 with ShopAIKey or Veo -> BLOCK
        job_t800_sak = {
            "product_type": "storyboard_to_video",
            "tier_id": 800,
            "selected_provider": "shopaikey_video",
        }
        with pytest.raises(RealVideoRenderError) as exc:
            _provider_order(job_t800_sak)
        assert "storyboard_cross_tier_override:800:shopaikey_video" in str(exc.value)

        job_t800_veo = {
            "product_type": "storyboard_to_video",
            "tier_id": 800,
            "selected_model": "veo3.1-fast",
        }
        with pytest.raises(RealVideoRenderError) as exc:
            _provider_order(job_t800_veo)
        assert "storyboard_cross_tier_override:800:veo3.1-fast" in str(exc.value)

        with pytest.raises(RealVideoRenderError) as exc:
            _resolve_storyboard_i2v_model(job_t800_veo)
        assert "storyboard_cross_tier_override:800:veo3.1-fast" in str(exc.value)

    def test_bot_prepare_project_for_invoice_fail_closed_and_cross_tier(self):
        """Verifies bot invoice preparation enforces fail-closed and blocks cross-tier overrides."""
        # Unsupported tiers fail closed (including 401, 700, 799, 801, 999)
        for tid in [401, 700, 799, 801, 999]:
            session_unsupported = {
                "flow_kind": "storyboard",
                "draft": {
                    "quality_tier": tid,
                    "b14_storyboard_plan": {"scenes": [{"scene_id": 1}]},
                },
            }
            with pytest.raises(ValueError) as exc:
                bot.video_b14_prepare_project_for_invoice(12345, session_unsupported)
            assert f"storyboard_unsupported_tier:{tid}" in str(exc.value)

        # Cross-tier override on Tier 400 with Kling
        session_cross_400 = {
            "flow_kind": "storyboard",
            "draft": {
                "b14_quality_xu": 400,
                "selected_model": "kling-v3",
                "b14_storyboard_plan": {"scenes": [{"scene_id": 1}]},
            },
        }
        with pytest.raises(ValueError) as exc:
            bot.video_b14_prepare_project_for_invoice(12345, session_cross_400)
        assert "storyboard_cross_tier_override:400:kling-v3" in str(exc.value)

        # Cross-tier override on Tier 800 with Veo
        session_cross_800 = {
            "flow_kind": "storyboard",
            "draft": {
                "b14_quality_xu": 800,
                "selected_model": "veo3.1-fast",
                "b14_storyboard_plan": {"scenes": [{"scene_id": 1}]},
            },
        }
        with pytest.raises(ValueError) as exc:
            bot.video_b14_prepare_project_for_invoice(12345, session_cross_800)
        assert "storyboard_cross_tier_override:800:veo3.1-fast" in str(exc.value)


class TestStoryboardDualTierEconomics:
    """Verifies the exact Owner-adjudicated pricing contracts for Tier 400 and Tier 800 in Storyboard."""

    def test_storyboard_tier_400_invoice_breakdown(self):
        inv = bot.video_b14_invoice_breakdown(400, 2, is_storyboard=True)
        assert inv["unit_xu"] == 371
        assert inv["subtotal_xu"] == 742
        assert inv["discount_percent"] == 10
        assert inv["discount_xu"] == 74
        assert inv["total_xu"] == 668

    def test_storyboard_tier_800_invoice_breakdown_owner_mandated(self):
        inv = bot.video_b14_invoice_breakdown(800, 2, is_storyboard=True)
        assert inv["unit_xu"] == 1714
        assert inv["subtotal_xu"] == 3428
        assert inv["discount_percent"] == 10
        assert inv["discount_xu"] == 342
        assert inv["total_xu"] == 3086

    def test_storyboard_tier_800_invoice_for_session(self):
        session = {
            "flow_kind": "storyboard",
            "topic": "Coffee promo",
            "aspect_ratio": "9:16",
            "draft": {
                "b14_quality_xu": 800,
                "scene_count": 2,
                "b14_storyboard_plan": {"scenes": [{"scene_id": 1}, {"scene_id": 2}]},
            },
        }
        invoice = bot.video_b14_invoice_for_session(session)
        assert invoice["quality_xu"] == 1714
        assert invoice["routing_quality_tier"] == 800
        assert invoice["scene_seconds"] == 8
        assert invoice["duration_seconds"] == 16
        assert invoice["subtotal_xu"] == 3428
        assert invoice["discount_xu"] == 342
        assert invoice["total_xu"] == 3086
        assert "Kling 8s" in invoice["package_label"]


class TestStoryboardDualTierRoutingResolution:
    """Proves resolution of providers and models for Tier 400 and Tier 800."""

    def test_tier_400_resolves_shopaikey_veo_fast(self, sample_panels):
        p1, p2 = sample_panels
        job = _build_storyboard_job(p1, p2, tier_id=400)
        order = _provider_order(job)
        assert order == ["shopaikey_video"], f"Expected ['shopaikey_video'], got {order}"
        model = _resolve_storyboard_i2v_model(job, provider=order[0])
        assert model == "veo3.1-fast", f"Expected 'veo3.1-fast', got {model}"
        assert model in STORYBOARD_PROVEN_I2V_MODELS_BY_PROVIDER["shopaikey_video"]

    def test_tier_800_resolves_key4u_kling_v3(self, sample_panels):
        p1, p2 = sample_panels
        job = _build_storyboard_job(p1, p2, tier_id=800)
        order = _provider_order(job)
        assert order == ["key4u_video"], f"Expected ['key4u_video'], got {order}"
        model = _resolve_storyboard_i2v_model(job, provider=order[0])
        assert model == "kling-v3", f"Expected 'kling-v3', got {model}"
        assert model in STORYBOARD_PROVEN_I2V_MODELS_BY_PROVIDER["key4u_video"]

    def test_legacy_internal_jobs_without_numeric_tier_use_model_override(self):
        """Legacy jobs without numeric tier retain model/provider resolution."""
        job_kling = {
            "product_type": "storyboard_prompt",
            "selected_model": "kling-v3",
        }
        assert _provider_order(job_kling) == ["key4u_video"]
        assert _resolve_storyboard_i2v_model(job_kling, provider="key4u_video") == "kling-v3"

        job_veo = {
            "product_type": "storyboard_prompt",
            "selected_model": "veo3.1-fast",
        }
        assert _provider_order(job_veo) == ["shopaikey_video"]
        assert _resolve_storyboard_i2v_model(job_veo, provider="shopaikey_video") == "veo3.1-fast"

    def test_legacy_internal_jobs_without_numeric_tier_use_provider_override(self):
        job_shopai = {
            "product_type": "storyboard_prompt",
            "selected_provider": "shopaikey_video",
        }
        assert _provider_order(job_shopai) == ["shopaikey_video"]
        assert _resolve_storyboard_i2v_model(job_shopai, provider="shopaikey_video") == "veo3.1-fast"

        job_k4u = {
            "product_type": "storyboard_prompt",
            "selected_provider": "key4u_video",
        }
        assert _provider_order(job_k4u) == ["key4u_video"]
        assert _resolve_storyboard_i2v_model(job_k4u, provider="key4u_video") == "kling-v3"


class TestStoryboardSpendAuthority:
    """Proves Storyboard spend authority via services/provider_spend_guard.py."""
    def test_storyboard_tier400_production_reservation_exact_and_bound_minus_1(self, tmp_path):
        """Proves Storyboard Tier 400 2 scenes exact reservation and bound-minus-1 enforcement."""
        db_path = str(tmp_path / "spend_t400.db")
        env = {
            "SPEND_GUARD_DB_PATH": db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "UNIT_TEST_ENV": "true",
        }
        psg.init_spend_guard_db(db_path=db_path, env=env)

        # Canonical Tier 400 2 scenes = 1,400,000 micro-USD (700,000 micro-USD per scene)
        # 1. BOUND EXACT (1,400,000 micro-USD cumulative for job)
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_t400_exact",
            product_family="Product Video",
            provider="shopaikey_video",
            tier="veo3.1-fast",
            user_id="user_400",
            job_id="job_t400_exact",
            request_id="req_t400_exact",
            operation="image_to_video",
            allowed_scene_slots="1,2",
            expected_max_provider_spend_micro_usd=1400000,
            db_path=db_path,
            env=env,
        )
        conf_s1 = create_bot_confirmation(
            mint_authority=create_test_mint_authority(
                chat_id="chat_400",
                user_id="user_400",
                job_id="job_t400_exact",
                request_id="req_t400_exact",
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_t400_exact",
                expected_max_provider_spend_usd=Decimal("1.40"),
            ),
            chat_id="chat_400",
            user_id="user_400",
            job_id="job_t400_exact",
            request_id="req_t400_exact",
            operation="image_to_video",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_t400_exact",
            expected_max_cost_usd=Decimal("1.40"),
            db_path=db_path,
            env=env,
        )
        ctx_s1 = psg.SpendGuardContext(
            job_id="job_t400_exact",
            request_id="req_t400_exact",
            trace_id="tr_t400_s1",
            chat_id="chat_400",
            user_id="user_400",
            scene_index=1,
            product_family="Product Video",
            provider="shopaikey_video",
            operation="image_to_video",
            model="veo3.1-fast",
            entrypoint="bot",
            user_flow="product_video_bot",
            bot_originated_action=True,
            is_paid_live_attempt=False,
            bot_confirm_authority=conf_s1,
            owner_receipt="rcpt_t400_exact",
            metadata={"quality_tier": 400, "product_type": "storyboard_prompt", "scene_count": 2, "duration_seconds": 8},
        )
        res_s1 = psg.reserve_provider_spend(ctx_s1, db_path=db_path, env=env)
        assert res_s1.allowed is True
        assert res_s1.cost_micro_usd == 700000

        conf_s2 = create_bot_confirmation(
            mint_authority=create_test_mint_authority(
                chat_id="chat_400",
                user_id="user_400",
                job_id="job_t400_exact",
                request_id="req_t400_exact",
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_t400_exact",
                expected_max_provider_spend_usd=Decimal("1.40"),
            ),
            chat_id="chat_400",
            user_id="user_400",
            job_id="job_t400_exact",
            request_id="req_t400_exact",
            operation="image_to_video",
            scene_index=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_t400_exact",
            expected_max_cost_usd=Decimal("1.40"),
            db_path=db_path,
            env=env,
        )
        ctx_s2 = psg.SpendGuardContext(
            job_id="job_t400_exact",
            request_id="req_t400_exact",
            trace_id="tr_t400_s2",
            chat_id="chat_400",
            user_id="user_400",
            scene_index=2,
            product_family="Product Video",
            provider="shopaikey_video",
            operation="image_to_video",
            model="veo3.1-fast",
            entrypoint="bot",
            user_flow="product_video_bot",
            bot_originated_action=True,
            is_paid_live_attempt=False,
            bot_confirm_authority=conf_s2,
            owner_receipt="rcpt_t400_exact",
            metadata={"quality_tier": 400, "product_type": "storyboard_prompt", "scene_count": 2, "duration_seconds": 8},
        )
        res_s2 = psg.reserve_provider_spend(ctx_s2, db_path=db_path, env=env)
        assert res_s2.allowed is True
        assert res_s2.cost_micro_usd == 700000
        assert res_s1.cost_micro_usd + res_s2.cost_micro_usd == 1400000

        # 2. BOUND - 1 MICRO: Child allocation 699,999 micro vs 700,000 canonical -> BLOCK
        conf_child_m1 = create_bot_confirmation(
            mint_authority=create_test_mint_authority(
                chat_id="chat_400",
                user_id="user_400",
                job_id="job_t400_minus1",
                request_id="req_t400_minus1",
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_t400_minus1",
                expected_max_provider_spend_usd=Decimal("0.699999"),
            ),
            chat_id="chat_400",
            user_id="user_400",
            job_id="job_t400_minus1",
            request_id="req_t400_minus1",
            operation="image_to_video",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_t400_minus1",
            expected_max_cost_usd=Decimal("0.699999"),
            db_path=db_path,
            env=env,
        )
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_t400_minus1",
            product_family="Product Video",
            provider="shopaikey_video",
            tier="veo3.1-fast",
            user_id="user_400",
            job_id="job_t400_minus1",
            request_id="req_t400_minus1",
            operation="image_to_video",
            allowed_scene_slots="1,2",
            expected_max_provider_spend_micro_usd=1400000,
            db_path=db_path,
            env=env,
        )
        ctx_child_m1 = psg.SpendGuardContext(
            job_id="job_t400_minus1",
            request_id="req_t400_minus1",
            trace_id="tr_t400_m1",
            chat_id="chat_400",
            user_id="user_400",
            scene_index=1,
            product_family="Product Video",
            provider="shopaikey_video",
            operation="image_to_video",
            model="veo3.1-fast",
            entrypoint="bot",
            user_flow="product_video_bot",
            bot_originated_action=True,
            is_paid_live_attempt=False,
            bot_confirm_authority=conf_child_m1,
            owner_receipt="rcpt_t400_minus1",
            metadata={"quality_tier": 400, "product_type": "storyboard_prompt", "scene_count": 2, "duration_seconds": 8},
        )
        res_child_m1 = psg.reserve_provider_spend(ctx_child_m1, db_path=db_path, env=env)
        assert res_child_m1.allowed is False
        assert res_child_m1.blocker == BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED

        # 3. BOUND - 1 MICRO: Cumulative Job budget 1,399,999 micro-USD (second scene exceeds) -> BLOCK
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_t400_job_m1",
            product_family="Product Video",
            provider="shopaikey_video",
            tier="veo3.1-fast",
            user_id="user_400",
            job_id="job_t400_job_m1",
            request_id="req_t400_job_m1",
            operation="image_to_video",
            allowed_scene_slots="1,2",
            expected_max_provider_spend_micro_usd=1399999,
            db_path=db_path,
            env=env,
        )
        conf_jm1_s1 = create_bot_confirmation(
            mint_authority=create_test_mint_authority(
                chat_id="chat_400",
                user_id="user_400",
                job_id="job_t400_job_m1",
                request_id="req_t400_job_m1",
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_t400_job_m1",
                expected_max_provider_spend_usd=Decimal("1.399999"),
            ),
            chat_id="chat_400",
            user_id="user_400",
            job_id="job_t400_job_m1",
            request_id="req_t400_job_m1",
            operation="image_to_video",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_t400_job_m1",
            expected_max_cost_usd=Decimal("1.399999"),
            db_path=db_path,
            env=env,
        )
        res_jm1_s1 = psg.reserve_provider_spend(
            psg.SpendGuardContext(
                job_id="job_t400_job_m1", request_id="req_t400_job_m1", trace_id="tr_jm1_1",
                chat_id="chat_400", user_id="user_400", scene_index=1, product_family="Product Video",
                provider="shopaikey_video", operation="image_to_video", model="veo3.1-fast",
                entrypoint="bot", user_flow="product_video_bot", bot_originated_action=True,
                is_paid_live_attempt=False, bot_confirm_authority=conf_jm1_s1, owner_receipt="rcpt_t400_job_m1",
                metadata={"quality_tier": 400, "product_type": "storyboard_prompt", "scene_count": 2, "duration_seconds": 8},
            ),
            db_path=db_path, env=env,
        )
        assert res_jm1_s1.allowed is True
        assert res_jm1_s1.cost_micro_usd == 700000

        conf_jm1_s2 = create_bot_confirmation(
            mint_authority=create_test_mint_authority(
                chat_id="chat_400",
                user_id="user_400",
                job_id="job_t400_job_m1",
                request_id="req_t400_job_m1",
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_t400_job_m1",
                expected_max_provider_spend_usd=Decimal("1.399999"),
            ),
            chat_id="chat_400",
            user_id="user_400",
            job_id="job_t400_job_m1",
            request_id="req_t400_job_m1",
            operation="image_to_video",
            scene_index=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_t400_job_m1",
            expected_max_cost_usd=Decimal("1.399999"),
            db_path=db_path,
            env=env,
        )
        res_jm1_s2 = psg.reserve_provider_spend(
            psg.SpendGuardContext(
                job_id="job_t400_job_m1", request_id="req_t400_job_m1", trace_id="tr_jm1_2",
                chat_id="chat_400", user_id="user_400", scene_index=2, product_family="Product Video",
                provider="shopaikey_video", operation="image_to_video", model="veo3.1-fast",
                entrypoint="bot", user_flow="product_video_bot", bot_originated_action=True,
                is_paid_live_attempt=False, bot_confirm_authority=conf_jm1_s2, owner_receipt="rcpt_t400_job_m1",
                metadata={"quality_tier": 400, "product_type": "storyboard_prompt", "scene_count": 2, "duration_seconds": 8},
            ),
            db_path=db_path, env=env,
        )
        assert res_jm1_s2.allowed is False
        assert res_jm1_s2.blocker == BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED

    def test_storyboard_tier800_production_reservation_exact_and_bound_minus_1(self, tmp_path):
        """Proves Storyboard Tier 800 2 scenes exact reservation and bound-minus-1 enforcement."""
        db_path = str(tmp_path / "spend_t800.db")
        env = {
            "SPEND_GUARD_DB_PATH": db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "UNIT_TEST_ENV": "true",
        }
        psg.init_spend_guard_db(db_path=db_path, env=env)

        # Canonical Tier 800 2 scenes = 24,480,196 micro-USD (12,240,098 micro-USD per scene)
        # 1. BOUND EXACT (24,480,196 micro-USD cumulative for job)
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_t800_exact",
            product_family="Product Video",
            provider="key4u_video",
            tier="kling-v3",
            user_id="user_800",
            job_id="job_t800_exact",
            request_id="req_t800_exact",
            operation="image_to_video",
            allowed_scene_slots="1,2",
            expected_max_provider_spend_micro_usd=24480196,
            db_path=db_path,
            env=env,
        )
        conf_s1 = create_bot_confirmation(
            mint_authority=create_test_mint_authority(
                chat_id="chat_800",
                user_id="user_800",
                job_id="job_t800_exact",
                request_id="req_t800_exact",
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_t800_exact",
                expected_max_provider_spend_usd=Decimal("24.480196"),
            ),
            chat_id="chat_800",
            user_id="user_800",
            job_id="job_t800_exact",
            request_id="req_t800_exact",
            operation="image_to_video",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_t800_exact",
            expected_max_cost_usd=Decimal("24.480196"),
            db_path=db_path,
            env=env,
        )
        ctx_s1 = psg.SpendGuardContext(
            job_id="job_t800_exact",
            request_id="req_t800_exact",
            trace_id="tr_t800_s1",
            chat_id="chat_800",
            user_id="user_800",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            operation="image_to_video",
            model="kling-v3",
            entrypoint="bot",
            user_flow="product_video_bot",
            bot_originated_action=True,
            is_paid_live_attempt=False,
            bot_confirm_authority=conf_s1,
            owner_receipt="rcpt_t800_exact",
            metadata={"quality_tier": 800, "product_type": "storyboard_prompt", "scene_count": 2, "duration_seconds": 8},
        )
        res_s1 = psg.reserve_provider_spend(ctx_s1, db_path=db_path, env=env)
        assert res_s1.allowed is True
        assert res_s1.cost_micro_usd == 12240098

        conf_s2 = create_bot_confirmation(
            mint_authority=create_test_mint_authority(
                chat_id="chat_800",
                user_id="user_800",
                job_id="job_t800_exact",
                request_id="req_t800_exact",
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_t800_exact",
                expected_max_provider_spend_usd=Decimal("24.480196"),
            ),
            chat_id="chat_800",
            user_id="user_800",
            job_id="job_t800_exact",
            request_id="req_t800_exact",
            operation="image_to_video",
            scene_index=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_t800_exact",
            expected_max_cost_usd=Decimal("24.480196"),
            db_path=db_path,
            env=env,
        )
        ctx_s2 = psg.SpendGuardContext(
            job_id="job_t800_exact",
            request_id="req_t800_exact",
            trace_id="tr_t800_s2",
            chat_id="chat_800",
            user_id="user_800",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            operation="image_to_video",
            model="kling-v3",
            entrypoint="bot",
            user_flow="product_video_bot",
            bot_originated_action=True,
            is_paid_live_attempt=False,
            bot_confirm_authority=conf_s2,
            owner_receipt="rcpt_t800_exact",
            metadata={"quality_tier": 800, "product_type": "storyboard_prompt", "scene_count": 2, "duration_seconds": 8},
        )
        res_s2 = psg.reserve_provider_spend(ctx_s2, db_path=db_path, env=env)
        assert res_s2.allowed is True
        assert res_s2.cost_micro_usd == 12240098
        assert res_s1.cost_micro_usd + res_s2.cost_micro_usd == 24480196

        # 2. BOUND - 1 MICRO: Child allocation 12,240,097 micro vs 12,240,098 canonical -> BLOCK
        conf_child_m1 = create_bot_confirmation(
            mint_authority=create_test_mint_authority(
                chat_id="chat_800",
                user_id="user_800",
                job_id="job_t800_minus1",
                request_id="req_t800_minus1",
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_t800_minus1",
                expected_max_provider_spend_usd=Decimal("12.240097"),
            ),
            chat_id="chat_800",
            user_id="user_800",
            job_id="job_t800_minus1",
            request_id="req_t800_minus1",
            operation="image_to_video",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_t800_minus1",
            expected_max_cost_usd=Decimal("12.240097"),
            db_path=db_path,
            env=env,
        )
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_t800_minus1",
            product_family="Product Video",
            provider="key4u_video",
            tier="kling-v3",
            user_id="user_800",
            job_id="job_t800_minus1",
            request_id="req_t800_minus1",
            operation="image_to_video",
            allowed_scene_slots="1,2",
            expected_max_provider_spend_micro_usd=24480196,
            db_path=db_path,
            env=env,
        )
        ctx_child_m1 = psg.SpendGuardContext(
            job_id="job_t800_minus1",
            request_id="req_t800_minus1",
            trace_id="tr_t800_m1",
            chat_id="chat_800",
            user_id="user_800",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            operation="image_to_video",
            model="kling-v3",
            entrypoint="bot",
            user_flow="product_video_bot",
            bot_originated_action=True,
            is_paid_live_attempt=False,
            bot_confirm_authority=conf_child_m1,
            owner_receipt="rcpt_t800_minus1",
            metadata={"quality_tier": 800, "product_type": "storyboard_prompt", "scene_count": 2, "duration_seconds": 8},
        )
        res_child_m1 = psg.reserve_provider_spend(ctx_child_m1, db_path=db_path, env=env)
        assert res_child_m1.allowed is False
        assert res_child_m1.blocker == BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED

        # 3. BOUND - 1 MICRO: Cumulative Job budget 24,480,195 micro-USD (second scene exceeds) -> BLOCK
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_t800_job_m1",
            product_family="Product Video",
            provider="key4u_video",
            tier="kling-v3",
            user_id="user_800",
            job_id="job_t800_job_m1",
            request_id="req_t800_job_m1",
            operation="image_to_video",
            allowed_scene_slots="1,2",
            expected_max_provider_spend_micro_usd=24480195,
            db_path=db_path,
            env=env,
        )
        conf_jm1_s1 = create_bot_confirmation(
            mint_authority=create_test_mint_authority(
                chat_id="chat_800",
                user_id="user_800",
                job_id="job_t800_job_m1",
                request_id="req_t800_job_m1",
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_t800_job_m1",
                expected_max_provider_spend_usd=Decimal("24.480195"),
            ),
            chat_id="chat_800",
            user_id="user_800",
            job_id="job_t800_job_m1",
            request_id="req_t800_job_m1",
            operation="image_to_video",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_t800_job_m1",
            expected_max_cost_usd=Decimal("24.480195"),
            db_path=db_path,
            env=env,
        )
        res_jm1_s1 = psg.reserve_provider_spend(
            psg.SpendGuardContext(
                job_id="job_t800_job_m1", request_id="req_t800_job_m1", trace_id="tr_jm1_1",
                chat_id="chat_800", user_id="user_800", scene_index=1, product_family="Product Video",
                provider="key4u_video", operation="image_to_video", model="kling-v3",
                entrypoint="bot", user_flow="product_video_bot", bot_originated_action=True,
                is_paid_live_attempt=False, bot_confirm_authority=conf_jm1_s1, owner_receipt="rcpt_t800_job_m1",
                metadata={"quality_tier": 800, "product_type": "storyboard_prompt", "scene_count": 2, "duration_seconds": 8},
            ),
            db_path=db_path, env=env,
        )
        assert res_jm1_s1.allowed is True
        assert res_jm1_s1.cost_micro_usd == 12240098

        conf_jm1_s2 = create_bot_confirmation(
            mint_authority=create_test_mint_authority(
                chat_id="chat_800",
                user_id="user_800",
                job_id="job_t800_job_m1",
                request_id="req_t800_job_m1",
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_t800_job_m1",
                expected_max_provider_spend_usd=Decimal("24.480195"),
            ),
            chat_id="chat_800",
            user_id="user_800",
            job_id="job_t800_job_m1",
            request_id="req_t800_job_m1",
            operation="image_to_video",
            scene_index=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_t800_job_m1",
            expected_max_cost_usd=Decimal("24.480195"),
            db_path=db_path,
            env=env,
        )
        res_jm1_s2 = psg.reserve_provider_spend(
            psg.SpendGuardContext(
                job_id="job_t800_job_m1", request_id="req_t800_job_m1", trace_id="tr_jm1_2",
                chat_id="chat_800", user_id="user_800", scene_index=2, product_family="Product Video",
                provider="key4u_video", operation="image_to_video", model="kling-v3",
                entrypoint="bot", user_flow="product_video_bot", bot_originated_action=True,
                is_paid_live_attempt=False, bot_confirm_authority=conf_jm1_s2, owner_receipt="rcpt_t800_job_m1",
                metadata={"quality_tier": 800, "product_type": "storyboard_prompt", "scene_count": 2, "duration_seconds": 8},
            ),
            db_path=db_path, env=env,
        )
        assert res_jm1_s2.allowed is False
        assert res_jm1_s2.blocker == BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED

    def test_storyboard_production_reservation_boundaries_and_fail_closed(self, tmp_path):
        """Proves WRONG_PROVIDER, WRONG_MODEL, WRONG_TIER, WRONG_DURATION block before provider."""
        db_path = str(tmp_path / "spend_mismatch.db")
        env = {
            "SPEND_GUARD_DB_PATH": db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "UNIT_TEST_ENV": "true",
        }
        psg.init_spend_guard_db(db_path=db_path, env=env)

        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_mismatch",
            product_family="Product Video",
            provider="shopaikey_video",
            tier="veo3.1-fast",
            user_id="user_mis",
            job_id="job_mis",
            request_id="req_mis",
            operation="image_to_video",
            allowed_scene_slots="*",
            expected_max_provider_spend_micro_usd=1400000,
            db_path=db_path,
            env=env,
        )
        conf_mis = create_bot_confirmation(
            mint_authority=create_test_mint_authority(
                chat_id="chat_mis",
                user_id="user_mis",
                job_id="job_mis",
                request_id="req_mis",
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_mismatch",
                expected_max_provider_spend_usd=Decimal("1.40"),
            ),
            chat_id="chat_mis",
            user_id="user_mis",
            job_id="job_mis",
            request_id="req_mis",
            operation="image_to_video",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_mismatch",
            expected_max_cost_usd=Decimal("1.40"),
            db_path=db_path,
            env=env,
        )

        # 1. WRONG_PROVIDER = BLOCK
        ctx_wp = psg.SpendGuardContext(
            job_id="job_mis", request_id="req_mis", trace_id="tr_wp",
            chat_id="chat_mis", user_id="user_mis", scene_index=1, product_family="Product Video",
            provider="unregistered_provider", operation="image_to_video", model="veo3.1-fast",
            entrypoint="bot", user_flow="product_video_bot", bot_originated_action=True,
            is_paid_live_attempt=False, bot_confirm_authority=conf_mis, owner_receipt="rcpt_mismatch",
            metadata={"quality_tier": 400},
        )
        res_wp = psg.reserve_provider_spend(ctx_wp, db_path=db_path, env=env)
        assert res_wp.allowed is False
        assert res_wp.blocker == "paid_transport_authority_unregistered"

        # 2. WRONG_MODEL = BLOCK
        ctx_wm = psg.SpendGuardContext(
            job_id="job_mis", request_id="req_mis", trace_id="tr_wm",
            chat_id="chat_mis", user_id="user_mis", scene_index=1, product_family="Product Video",
            provider="shopaikey_video", operation="image_to_video", model="unregistered_model",
            entrypoint="bot", user_flow="product_video_bot", bot_originated_action=True,
            is_paid_live_attempt=False, bot_confirm_authority=conf_mis, owner_receipt="rcpt_mismatch",
            metadata={"quality_tier": 400},
        )
        res_wm = psg.reserve_provider_spend(ctx_wm, db_path=db_path, env=env)
        assert res_wm.allowed is False
        assert res_wm.blocker == "provider_max_cost_authority_missing"

        # 3. WRONG_TIER = BLOCK (tier=999)
        ctx_wt = psg.SpendGuardContext(
            job_id="job_mis", request_id="req_mis", trace_id="tr_wt",
            chat_id="chat_mis", user_id="user_mis", scene_index=1, product_family="Product Video",
            provider="shopaikey_video", operation="image_to_video", model="veo3.1-fast",
            entrypoint="bot", user_flow="product_video_bot", bot_originated_action=True,
            is_paid_live_attempt=False, bot_confirm_authority=conf_mis, owner_receipt="rcpt_mismatch",
            metadata={"quality_tier": 999},
        )
        res_wt = psg.reserve_provider_spend(ctx_wt, db_path=db_path, env=env)
        assert res_wt.allowed is False
        assert res_wt.blocker == "provider_max_cost_authority_missing"

        # 4. WRONG_DURATION = BLOCK (duration_seconds=999 in Storyboard 8s contract)
        ctx_wd = psg.SpendGuardContext(
            job_id="job_mis", request_id="req_mis", trace_id="tr_wd",
            chat_id="chat_mis", user_id="user_mis", scene_index=1, product_family="Product Video",
            provider="shopaikey_video", operation="image_to_video", model="veo3.1-fast",
            entrypoint="bot", user_flow="product_video_bot", bot_originated_action=True,
            is_paid_live_attempt=False, bot_confirm_authority=conf_mis, owner_receipt="rcpt_mismatch",
            metadata={"quality_tier": 400, "duration_seconds": 999, "product_type": "storyboard_prompt"},
        )
        res_wd = psg.reserve_provider_spend(ctx_wd, db_path=db_path, env=env)
        assert res_wd.allowed is False
        assert res_wd.blocker == "provider_max_cost_authority_missing"

    def test_caller_metadata_cannot_raise_canonical_bound(self, tmp_path):
        """Proves CALLER_METADATA_CANNOT_RAISE_CANONICAL_BOUND=PASS."""
        mint = create_test_mint_authority(
            chat_id="chat_inf",
            user_id="user_inf",
            job_id="job_inf",
            request_id="req_inf",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_inf",
            expected_max_provider_spend_usd=Decimal("1.40"),
        )
        # Attempting to forge an inflated expected_max_cost_usd raises PermissionError unconditionally
        with pytest.raises(PermissionError) as exc_info:
            create_bot_confirmation(
                mint_authority=mint,
                chat_id="chat_inf",
                user_id="user_inf",
                job_id="job_inf",
                request_id="req_inf",
                operation="image_to_video",
                scene_index=1,
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_inf",
                expected_max_cost_usd=Decimal("999.00"),
            )
        assert "CALLER_CAN_OVERRIDE_EXPECTED_MAX_SPEND=NO" in str(exc_info.value)


    def test_storyboard_tier400_spend_authority(self):
        auth = psg.resolve_paid_transport_authority("Product Video", "shopaikey_video", "create_video_task")
        assert auth is not None

        ctx = psg.SpendGuardContext(
            product_family="Product Video",
            provider="shopaikey_video",
            model="veo3.1-fast",
            operation="create_video_task",
            metadata={
                "product_type": "storyboard_prompt",
                "tier_id": 400,
                "duration_seconds": 8,
                "scene_count": 2,
            },
        )
        cost_micro, proven, source = psg.resolve_canonical_cost_micro_usd(ctx, auth)
        assert proven is True
        assert cost_micro == 1_400_000  # $1.40 for 2 scenes
        assert "veo3.1-fast:8s" in source

    def test_storyboard_tier800_spend_authority(self):
        auth = psg.resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        assert auth is not None

        ctx = psg.SpendGuardContext(
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            metadata={
                "product_type": "storyboard_prompt",
                "tier_id": 800,
                "duration_seconds": 8,
                "scene_count": 2,
            },
        )
        cost_micro, proven, source = psg.resolve_canonical_cost_micro_usd(ctx, auth)
        assert proven is True
        assert cost_micro == 24_480_196  # $24.48019584 for 2 scenes
        assert "kling-v3:8s" in source

    def test_storyboard_spend_authority_boundaries_and_fail_closed(self):
        auth_k4u = psg.resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        auth_sak = psg.resolve_paid_transport_authority("Product Video", "shopaikey_video", "create_video_task")

        # WRONG_PROVIDER = BLOCK
        ctx_wrong_prov = psg.SpendGuardContext(
            product_family="Product Video",
            provider="key4u_video",
            model="veo3.1-fast",
            operation="create_video_task",
            metadata={"product_type": "storyboard_prompt", "tier_id": 400, "duration_seconds": 8, "scene_count": 2},
        )
        cost, proven, source = psg.resolve_canonical_cost_micro_usd(ctx_wrong_prov, auth_k4u)
        assert proven is False
        assert "storyboard_tier_provider_mismatch:400" in source

        # WRONG_MODEL = BLOCK
        ctx_wrong_model = psg.SpendGuardContext(
            product_family="Product Video",
            provider="key4u_video",
            model="veo3.1-fast",
            operation="create_video_task",
            metadata={"product_type": "storyboard_prompt", "tier_id": 800, "duration_seconds": 8, "scene_count": 2},
        )
        cost, proven, source = psg.resolve_canonical_cost_micro_usd(ctx_wrong_model, auth_k4u)
        assert proven is False
        assert "storyboard_tier_model_mismatch:800" in source

        # WRONG_TIER = BLOCK
        ctx_wrong_tier = psg.SpendGuardContext(
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            metadata={"product_type": "storyboard_prompt", "tier_id": 700, "duration_seconds": 8, "scene_count": 2},
        )
        cost, proven, source = psg.resolve_canonical_cost_micro_usd(ctx_wrong_tier, auth_k4u)
        assert proven is False
        assert "storyboard_unsupported_tier:700" in source

        # WRONG_DURATION = BLOCK (e.g. 10s on Storyboard 8s contract)
        ctx_wrong_dur = psg.SpendGuardContext(
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            metadata={"product_type": "storyboard_prompt", "tier_id": 800, "duration_seconds": 10, "scene_count": 2},
        )
        cost, proven, source = psg.resolve_canonical_cost_micro_usd(ctx_wrong_dur, auth_k4u)
        assert proven is False
        assert "storyboard_tier_duration_mismatch:800" in source

        # CALLER_METADATA_CANNOT_RAISE_BOUND = PASS
        ctx_caller_inflation = psg.SpendGuardContext(
            product_family="Product Video",
            provider="shopaikey_video",
            model="veo3.1-fast",
            operation="create_video_task",
            estimated_max_cost_usd=999.0,
            metadata={
                "product_type": "storyboard_prompt",
                "tier_id": 400,
                "duration_seconds": 8,
                "scene_count": 2,
                "cost_usd": 999.0,
            },
        )
        cost, proven, _ = psg.resolve_canonical_cost_micro_usd(ctx_caller_inflation, auth_sak)
        assert proven is True
        assert cost == 1_400_000  # Stays strictly 1,400,000 micro-USD despite caller metadata


class TestStoryboardDualTierRenderProgression:
    """Proves mock render execution on both Tier 400 and Tier 800 with zero real provider calls."""

    MOCK_ENV = {
        "BOT_ENV": "test",
        "KEY4U_API_KEY": "test_k4u_sec_key",
        "KEY4U_VIDEO_ENABLED": "1",
        "SHOPAIKEY_API_KEY": "test_sak_sec_key",
    }

    def test_tier_400_shopaikey_mock_render_success(self, sample_panels, tmp_path):
        p1, p2 = sample_panels
        job = _build_storyboard_job(p1, p2, tier_id=400, job_id=4401, project_id=4401)
        job["selected_provider"] = "shopaikey_video"
        job["selected_model"] = "veo3.1-fast"
        job["provider_order"] = ["shopaikey_video"]

        captured_requests = []
        def mock_run_provider_400(req, **kwargs):
            captured_requests.append(req)
            scene_idx = req.metadata.get("scene_index") or len(captured_requests)
            raw_output_path = req.metadata.get("raw_output_path") or str(tmp_path / f"scene_400_{scene_idx:02d}.mp4")
            Path(raw_output_path).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
            return {
                "ok": True,
                "status": "completed",
                "provider": "shopaikey_video",
                "model": "veo3.1-fast",
                "output_path": raw_output_path,
                "raw_output_path": raw_output_path,
            }

        def mock_finalize_clips(**kwargs):
            final_mp4 = str(tmp_path / "final_16s.mp4")
            Path(final_mp4).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)
            return {
                "ok": True,
                "status": "completed",
                "final_video_path": final_mp4,
                "output_path": final_mp4,
                "final_output_path": final_mp4,
                "duration_sec": 16.0,
                "final_duration_seconds": 16,
                "aspect_ratio": "9:16",
            }

        def mock_probe_video(path, *args, **kwargs):
            d = 16.0 if "final" in str(path) else 8.0
            return {"ok": True, "duration_sec": d, "duration": d, "bytes": 512, "has_audio": True, "has_video": True, "width": 1080, "height": 1920}

        def mock_normalize(src, dst, *args, **kwargs):
            Path(dst).write_bytes(Path(src).read_bytes())
            return dst

        render_workspace = str(tmp_path / "render_work_400")
        with patch.dict(os.environ, self.MOCK_ENV), \
             patch("services.multiscene_video_pipeline.normalize_scene_duration", side_effect=mock_normalize), \
             patch("services.multiscene_video_pipeline.probe_duration", side_effect=lambda p: 16.0 if "final" in str(p) else 8.0), \
             patch("services.multiscene_video_pipeline.probe_media_streams", return_value={"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}), \
             patch("services.video_local_validation.probe_video_file", side_effect=mock_probe_video), \
             patch("services.video_final_output.probe_video", side_effect=mock_probe_video), \
             patch("services.video_real_render_connector.run_provider_generation", side_effect=mock_run_provider_400), \
             patch("services.video_real_render_connector.finalize_multiscene_scene_clips", side_effect=mock_finalize_clips), \
             patch("services.video_real_render_connector._addon_plan", return_value={}):
            res = render_real_video_job(job, render_workspace)

        assert res["ok"] is True
        assert res["status"] == "completed"
        assert res["final_duration_seconds"] == 16
        assert len(captured_requests) == 2

    def test_tier_800_key4u_mock_render_success(self, sample_panels, tmp_path):
        p1, p2 = sample_panels
        job = _build_storyboard_job(p1, p2, tier_id=800, job_id=8801, project_id=8801)
        job["selected_provider"] = "key4u_video"
        job["selected_model"] = "kling-v3"
        job["provider_order"] = ["key4u_video"]

        captured_requests = []
        def mock_run_provider_800(req, **kwargs):
            captured_requests.append(req)
            scene_idx = req.metadata.get("scene_index") or len(captured_requests)
            raw_output_path = req.metadata.get("raw_output_path") or str(tmp_path / f"scene_800_{scene_idx:02d}.mp4")
            Path(raw_output_path).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
            return {
                "ok": True,
                "status": "completed",
                "provider": "key4u_video",
                "model": "kling-v3",
                "output_path": raw_output_path,
                "raw_output_path": raw_output_path,
            }

        def mock_finalize_clips(**kwargs):
            final_mp4 = str(tmp_path / "final_kling_16s.mp4")
            Path(final_mp4).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)
            return {
                "ok": True,
                "status": "completed",
                "final_video_path": final_mp4,
                "output_path": final_mp4,
                "final_output_path": final_mp4,
                "duration_sec": 16.0,
                "final_duration_seconds": 16,
                "aspect_ratio": "9:16",
            }

        def mock_probe_video(path, *args, **kwargs):
            d = 16.0 if "final" in str(path) else 8.0
            return {"ok": True, "duration_sec": d, "duration": d, "bytes": 512, "has_audio": True, "has_video": True, "width": 1080, "height": 1920}

        def mock_normalize(src, dst, *args, **kwargs):
            Path(dst).write_bytes(Path(src).read_bytes())
            return dst

        render_workspace = str(tmp_path / "render_work_800")
        with patch.dict(os.environ, self.MOCK_ENV), \
             patch("services.multiscene_video_pipeline.normalize_scene_duration", side_effect=mock_normalize), \
             patch("services.multiscene_video_pipeline.probe_duration", side_effect=lambda p: 16.0 if "final" in str(p) else 8.0), \
             patch("services.multiscene_video_pipeline.probe_media_streams", return_value={"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}), \
             patch("services.video_local_validation.probe_video_file", side_effect=mock_probe_video), \
             patch("services.video_final_output.probe_video", side_effect=mock_probe_video), \
             patch("services.video_real_render_connector.run_provider_generation", side_effect=mock_run_provider_800), \
             patch("services.video_real_render_connector.finalize_multiscene_scene_clips", side_effect=mock_finalize_clips), \
             patch("services.video_real_render_connector._addon_plan", return_value={}):
            res = render_real_video_job(job, render_workspace)

        assert res["ok"] is True
        assert res["status"] == "completed"
        assert res["final_duration_seconds"] == 16
        assert len(captured_requests) == 2

    def test_both_tiers_fail_closed_without_fallback_leaks(self, sample_panels, tmp_path):
        p1, p2 = sample_panels

        # Tier 400 failure terminates with shopaikey diagnostic, does NOT fall back to Key4U
        job400 = _build_storyboard_job(p1, p2, tier_id=400, job_id=4402, project_id=4402)
        mock_fail400 = MagicMock(side_effect=RealVideoRenderError(
            "shopaikey_upstream_timeout",
            diagnostics={"ok": False, "provider": "shopaikey_video", "model": "veo3.1-fast", "blocker": "shopaikey_upstream_timeout", "scene_index": 1}
        ))
        with patch.dict(os.environ, self.MOCK_ENV), \
             patch("services.video_real_render_connector.run_provider_generation", mock_fail400), \
             patch("services.video_real_render_connector._addon_plan", return_value={}):
            try:
                res400 = render_real_video_job(job400, str(tmp_path / "work400"))
            except RealVideoRenderError as exc:
                res400 = {"ok": False, "error": str(exc), "actual_provider_payload_status": str(exc), "fallback_used": False}
            assert res400.get("ok") is False
            assert bool(res400.get("fallback_used")) is False
            assert "shopaikey_upstream_timeout" in str(res400.get("actual_provider_payload_status") or res400.get("provider_error") or res400.get("blocker"))
            assert mock_fail400.call_count >= 1
            for call in mock_fail400.call_args_list:
                req = call[0][0]
                model = getattr(req, "model", None) or (getattr(req, "metadata", {}) or {}).get("model")
                assert model == "veo3.1-fast"

        # Tier 800 failure terminates with key4u diagnostic, does NOT fall back to ShopAIKey
        job800 = _build_storyboard_job(p1, p2, tier_id=800, job_id=8802, project_id=8802)
        mock_fail800 = MagicMock(side_effect=RealVideoRenderError(
            "key4u_kling_quota_exhausted",
            diagnostics={"ok": False, "provider": "key4u_video", "model": "kling-v3", "blocker": "key4u_kling_quota_exhausted", "scene_index": 1}
        ))
        with patch.dict(os.environ, self.MOCK_ENV), \
             patch("services.video_real_render_connector.run_provider_generation", mock_fail800), \
             patch("services.video_real_render_connector._addon_plan", return_value={}):
            try:
                res800 = render_real_video_job(job800, str(tmp_path / "work800"))
            except RealVideoRenderError as exc:
                res800 = {"ok": False, "error": str(exc), "actual_provider_payload_status": str(exc), "fallback_used": False}
            assert res800.get("ok") is False
            assert bool(res800.get("fallback_used")) is False
            assert "key4u_kling_quota_exhausted" in str(res800.get("actual_provider_payload_status") or res800.get("provider_error") or res800.get("blocker"))
            assert mock_fail800.call_count >= 1
            for call in mock_fail800.call_args_list:
                req = call[0][0]
                model = getattr(req, "model", None) or (getattr(req, "metadata", {}) or {}).get("model")
                assert model == "kling-v3"



class TestExactModelContractFailClosed:
    """Canonical Storyboard Direction A exact model contract fail-closed tests."""

    def test_tier400_exact_model_contract_allow_and_blocks(self):
        job = {"product_type": "storyboard_to_video", "quality_tier": 400}

        # TIER400_MODEL_VEO31_FAST=ALLOW
        job_veo = dict(job, selected_model="veo3.1-fast")
        assert _resolve_storyboard_i2v_model(job_veo, provider="shopaikey_video") == "veo3.1-fast"

        # TIER400_MODEL_KLING_V3=BLOCK
        job_kling = dict(job, selected_model="kling-v3")
        with pytest.raises(RealVideoRenderError) as exc_info:
            _resolve_storyboard_i2v_model(job_kling, provider="shopaikey_video")
        assert "storyboard_cross_tier_override:400:kling-v3" in str(exc_info.value)

        # TIER400_MODEL_KLING_3_0_TURBO=BLOCK
        job_kling_turbo = dict(job, selected_model="kling-3.0-turbo")
        with pytest.raises(RealVideoRenderError) as exc_info:
            _resolve_storyboard_i2v_model(job_kling_turbo, provider="shopaikey_video")
        assert "storyboard_cross_tier_override:400:kling-3.0-turbo" in str(exc_info.value)

        # TIER400_MODEL_KEY4U_VEO_UNDERSCORE=BLOCK
        job_veo_underscore = dict(job, selected_model="veo_3_1-fast")
        with pytest.raises(RealVideoRenderError) as exc_info:
            _resolve_storyboard_i2v_model(job_veo_underscore, provider="shopaikey_video")
        assert "storyboard_cross_tier_override:400:veo_3_1-fast" in str(exc_info.value)

    def test_tier800_exact_model_contract_allow_and_blocks(self):
        job = {"product_type": "storyboard_to_video", "quality_tier": 800}

        # TIER800_MODEL_KLING_V3=ALLOW
        job_kling = dict(job, selected_model="kling-v3")
        assert _resolve_storyboard_i2v_model(job_kling, provider="key4u_video") == "kling-v3"

        # TIER800_MODEL_VEO31_FAST=BLOCK
        job_veo = dict(job, selected_model="veo3.1-fast")
        with pytest.raises(RealVideoRenderError) as exc_info:
            _resolve_storyboard_i2v_model(job_veo, provider="key4u_video")
        assert "storyboard_cross_tier_override:800:veo3.1-fast" in str(exc_info.value)

        # TIER800_MODEL_KLING_3_0_TURBO=BLOCK (No silent coercion to kling-v3)
        job_kling_turbo = dict(job, selected_model="kling-3.0-turbo")
        with pytest.raises(RealVideoRenderError) as exc_info:
            _resolve_storyboard_i2v_model(job_kling_turbo, provider="key4u_video")
        assert "storyboard_cross_tier_override:800:kling-3.0-turbo" in str(exc_info.value)

    def test_spend_guard_exact_model_cost_resolution(self):
        auth_shopai = psg.resolve_paid_transport_authority("Product Video", "shopaikey_video", "image_to_video")
        auth_key4u = psg.resolve_paid_transport_authority("Product Video", "key4u_video", "image_to_video")

        def _cost(prov, mod, dur, tier):
            auth = auth_shopai if "shopai" in prov else auth_key4u
            ctx = psg.SpendGuardContext(
                job_id="j", request_id="r", trace_id="t", chat_id="c", user_id="u",
                scene_index=1, product_family="Product Video", provider=prov,
                operation="image_to_video", model=mod, entrypoint="bot",
                user_flow="product_video_bot", bot_originated_action=True,
                is_paid_live_attempt=False, owner_receipt="rcpt",
                metadata={"quality_tier": tier, "product_type": "storyboard_prompt", "duration_seconds": dur},
            )
            cost, ok, reason = psg.resolve_canonical_cost_micro_usd(ctx, auth)
            return cost if ok else 0

        # Tier 400: Veo exact allow; others 0 (blocked)
        assert _cost("shopaikey_video", "veo3.1-fast", 8, 400) == 700000
        assert _cost("shopaikey_video", "kling-v3", 8, 400) == 0
        assert _cost("shopaikey_video", "kling-3.0-turbo", 8, 400) == 0
        assert _cost("shopaikey_video", "veo_3_1-fast", 8, 400) == 0

        # Tier 800: Kling exact allow; others 0 (blocked)
        assert _cost("key4u_video", "kling-v3", 8, 800) == 12240098
        assert _cost("key4u_video", "kling-video", 8, 800) == 12240098
        assert _cost("key4u_video", "veo3.1-fast", 8, 800) == 0
        assert _cost("key4u_video", "kling-3.0-turbo", 8, 800) == 0

    def test_bot_invoice_preparation_cross_tier_override_fail_closed(self):
        session_bad_400 = {
            "draft": {
                "b14_quality_xu": 400,
                "b14_selected_provider": "shopaikey_video",
                "b14_selected_model": "kling-v3",
                "b14_storyboard_plan": {"scenes": [{"scene_id": 1}]},
            }
        }
        with pytest.raises(ValueError) as exc:
            bot.video_b14_prepare_project_for_invoice(12345, session_bad_400)
        assert "storyboard_cross_tier_override:400" in str(exc.value)

        session_bad_800 = {
            "draft": {
                "b14_quality_xu": 800,
                "b14_selected_provider": "key4u_video",
                "b14_selected_model": "kling-3.0-turbo",
                "b14_storyboard_plan": {"scenes": [{"scene_id": 1}]},
            }
        }
        with pytest.raises(ValueError) as exc:
            bot.video_b14_prepare_project_for_invoice(12345, session_bad_800)
        assert "storyboard_cross_tier_override:800" in str(exc.value)

    def test_spend_guard_production_reservations(self, tmp_path):
        db_path = str(tmp_path / "spend_guard_res.db")
        env = {
            "SPEND_GUARD_DB_PATH": db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "UNIT_TEST_ENV": "true",
        }
        psg.init_spend_guard_db(db_path=db_path, env=env)

        # Create valid authorizations for test
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_prod_sb",
            product_family="Product Video",
            provider="key4u_video",
            tier="kling-v3",
            user_id="user_sb",
            job_id="job_prod_sb",
            request_id="req_prod_sb",
            operation="image_to_video",
            allowed_scene_slots="1",
            expected_max_provider_spend_micro_usd=24480196,
            db_path=db_path,
            env=env,
        )

        conf_sb = psg.create_bot_confirmation(
            mint_authority=create_test_mint_authority(
                chat_id="chat_sb", user_id="user_sb", job_id="job_prod_sb",
                request_id="req_prod_sb", purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_prod_sb", expected_max_provider_spend_usd=Decimal("24.480196"),
            ),
            chat_id="chat_sb", user_id="user_sb", job_id="job_prod_sb", request_id="req_prod_sb",
            operation="image_to_video", scene_index=1, purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_prod_sb", expected_max_cost_usd=Decimal("24.480196"),
            db_path=db_path, env=env,
        )

        # 1. TIER800_KLING_V3_RESERVATION=ALLOW_TEST_SAFE
        ctx_800_kling = psg.SpendGuardContext(
            job_id="job_prod_sb", request_id="req_prod_sb", trace_id="tr_800_k",
            chat_id="chat_sb", user_id="user_sb", scene_index=1, product_family="Product Video",
            provider="key4u_video", operation="image_to_video", model="kling-v3",
            entrypoint="bot", user_flow="product_video_bot", bot_originated_action=True,
            is_paid_live_attempt=False, bot_confirm_authority=conf_sb, owner_receipt="rcpt_prod_sb",
            metadata={"quality_tier": 800, "product_type": "storyboard_prompt", "duration_seconds": 8},
        )
        res_800_kling = psg.reserve_provider_spend(ctx_800_kling, db_path=db_path, env=env)
        assert res_800_kling.allowed is True
        assert res_800_kling.cost_micro_usd == 12240098

        # 2. TIER800_KLING_3_0_TURBO_RESERVATION=BLOCK
        ctx_800_turbo = psg.SpendGuardContext(
            job_id="job_prod_sb", request_id="req_prod_sb", trace_id="tr_800_t",
            chat_id="chat_sb", user_id="user_sb", scene_index=1, product_family="Product Video",
            provider="key4u_video", operation="image_to_video", model="kling-3.0-turbo",
            entrypoint="bot", user_flow="product_video_bot", bot_originated_action=True,
            is_paid_live_attempt=False, bot_confirm_authority=conf_sb, owner_receipt="rcpt_prod_sb",
            metadata={"quality_tier": 800, "product_type": "storyboard_prompt", "duration_seconds": 8},
        )
        res_800_turbo = psg.reserve_provider_spend(ctx_800_turbo, db_path=db_path, env=env)
        assert res_800_turbo.allowed is False
        assert res_800_turbo.cost_micro_usd == 0

        # 3. TIER800_VEO_RESERVATION=BLOCK
        ctx_800_veo = psg.SpendGuardContext(
            job_id="job_prod_sb", request_id="req_prod_sb", trace_id="tr_800_v",
            chat_id="chat_sb", user_id="user_sb", scene_index=1, product_family="Product Video",
            provider="key4u_video", operation="image_to_video", model="veo3.1-fast",
            entrypoint="bot", user_flow="product_video_bot", bot_originated_action=True,
            is_paid_live_attempt=False, bot_confirm_authority=conf_sb, owner_receipt="rcpt_prod_sb",
            metadata={"quality_tier": 800, "product_type": "storyboard_prompt", "duration_seconds": 8},
        )
        res_800_veo = psg.reserve_provider_spend(ctx_800_veo, db_path=db_path, env=env)
        assert res_800_veo.allowed is False
        assert res_800_veo.cost_micro_usd == 0

        # Now for Tier 400
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_prod_400",
            product_family="Product Video",
            provider="shopaikey_video",
            tier="veo3.1-fast",
            user_id="user_400",
            job_id="job_prod_400",
            request_id="req_prod_400",
            operation="image_to_video",
            allowed_scene_slots="1",
            expected_max_provider_spend_micro_usd=1400000,
            db_path=db_path,
            env=env,
        )
        conf_400 = psg.create_bot_confirmation(
            mint_authority=create_test_mint_authority(
                chat_id="chat_400", user_id="user_400", job_id="job_prod_400",
                request_id="req_prod_400", purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_prod_400", expected_max_provider_spend_usd=Decimal("1.40"),
            ),
            chat_id="chat_400", user_id="user_400", job_id="job_prod_400", request_id="req_prod_400",
            operation="image_to_video", scene_index=1, purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_prod_400", expected_max_cost_usd=Decimal("1.40"),
            db_path=db_path, env=env,
        )

        # 4. TIER400_VEO31_FAST_RESERVATION=ALLOW_TEST_SAFE
        ctx_400_veo = psg.SpendGuardContext(
            job_id="job_prod_400", request_id="req_prod_400", trace_id="tr_400_v",
            chat_id="chat_400", user_id="user_400", scene_index=1, product_family="Product Video",
            provider="shopaikey_video", operation="image_to_video", model="veo3.1-fast",
            entrypoint="bot", user_flow="product_video_bot", bot_originated_action=True,
            is_paid_live_attempt=False, bot_confirm_authority=conf_400, owner_receipt="rcpt_prod_400",
            metadata={"quality_tier": 400, "product_type": "storyboard_prompt", "duration_seconds": 8},
        )
        res_400_veo = psg.reserve_provider_spend(ctx_400_veo, db_path=db_path, env=env)
        assert res_400_veo.allowed is True
        assert res_400_veo.cost_micro_usd == 700000

        # 5. TIER400_KLING_RESERVATION=BLOCK
        ctx_400_kling = psg.SpendGuardContext(
            job_id="job_prod_400", request_id="req_prod_400", trace_id="tr_400_k",
            chat_id="chat_400", user_id="user_400", scene_index=1, product_family="Product Video",
            provider="shopaikey_video", operation="image_to_video", model="kling-v3",
            entrypoint="bot", user_flow="product_video_bot", bot_originated_action=True,
            is_paid_live_attempt=False, bot_confirm_authority=conf_400, owner_receipt="rcpt_prod_400",
            metadata={"quality_tier": 400, "product_type": "storyboard_prompt", "duration_seconds": 8},
        )
        res_400_kling = psg.reserve_provider_spend(ctx_400_kling, db_path=db_path, env=env)
        assert res_400_kling.allowed is False
        assert res_400_kling.cost_micro_usd == 0


class TestWorkerPayloadTierLineageAndDirectionA:
    """Proves build_worker_job_payload tier lineage, unmasking, and Direction A defaults."""

    def test_worker_payload_storyboard_tier400_preserved(self):
        job = {
            "product_type": "storyboard_to_video",
            "quality_tier": 400,
            "project": {"product_type": "storyboard_to_video"},
        }
        payload = remote_worker_api.build_worker_job_payload(job)
        assert payload.get("quality_tier") == 400
        assert payload.get("tier_id") == 400
        assert payload.get("selected_provider") == "shopaikey_video"
        assert payload.get("selected_model") == "veo3.1-fast"

    def test_worker_payload_storyboard_tier800_preserved(self):
        job = {
            "product_type": "storyboard_to_video",
            "quality_tier": 800,
            "project": {"product_type": "storyboard_to_video"},
        }
        payload = remote_worker_api.build_worker_job_payload(job)
        assert payload.get("quality_tier") == 800
        assert payload.get("tier_id") == 800
        assert payload.get("selected_provider") == "key4u_video"
        assert payload.get("selected_model") == "kling-v3"

    def test_worker_payload_storyboard_unsupported_tier999_preserved(self):
        job = {
            "product_type": "storyboard_to_video",
            "quality_tier": 999,
            "project": {"product_type": "storyboard_to_video"},
        }
        payload = remote_worker_api.build_worker_job_payload(job)
        assert payload.get("quality_tier") == 999
        assert payload.get("tier_id") == 999

    def test_worker_payload_quality_tier_common_does_not_mask_numeric_tier800(self):
        job = {
            "product_type": "storyboard_to_video",
            "quality_tier": "common",
            "project": {
                "product_type": "storyboard_to_video",
                "asset_pack_json": json.dumps({"tier_id": 800}),
            },
        }
        payload = remote_worker_api.build_worker_job_payload(job)
        assert payload.get("quality_tier") == 800
        assert payload.get("tier_id") == 800
        assert payload.get("selected_provider") == "key4u_video"
        assert payload.get("selected_model") == "kling-v3"

    def test_worker_payload_quality_tier_common_does_not_mask_numeric_tier999(self):
        job = {
            "product_type": "storyboard_to_video",
            "quality_tier": "common",
            "project": {
                "product_type": "storyboard_to_video",
                "invoice_json": json.dumps({"tier_id": 999}),
            },
        }
        payload = remote_worker_api.build_worker_job_payload(job)
        assert payload.get("quality_tier") == 999
        assert payload.get("tier_id") == 999
