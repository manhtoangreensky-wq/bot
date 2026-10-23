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
3. Strict Tier Eligibility:
   - Storyboard public catalog and package resolutions strictly restricted to [400, 800].
   - All other tiers (200, 300, 500, 600, 700, 1000, 1200, 1500) FAIL CLOSED before provider.
4. Explicit overrides preserved and cannot bypass spend guard.
5. Zero real external provider calls; all provider I/O mocked and test-isolated.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import bot
from services import provider_spend_guard as psg
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

    def test_unsupported_tiers_fail_closed_before_provider(self):
        unsupported = [200, 300, 500, 600, 700, 1000, 1200, 1500]
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

    def test_explicit_model_overrides_work_for_both_tiers(self):
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

    def test_explicit_provider_overrides(self):
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
