"""Tests for P0.PRODUCT_VIDEO_STORYBOARD_DUAL_TIER_ROUTING.

Verifies the Owner-approved dual-tier routing architecture for Storyboard:
1. Option B (Standard / Budget / Fast / Tier 400):
   Routes to shopaikey_video with veo3.1-fast ($0.70/scene, $1.40 for 2 scenes).
2. Option A (Pro / High Quality / Studio / Tier 800):
   Routes to key4u_video with kling-v3 ($12.24/scene, $24.48 for 2 scenes).
3. Both tiers operate independently without conflict, zero fallback leaks, and fail closed.
4. Zero real external provider calls; all provider I/O mocked and test-isolated.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services import provider_spend_guard as psg
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
            "local_path": panel1,
            "video_prompt": "Scene 1: Robot walks on Martian surface",
            "duration_seconds": 8.0,
            "aspect_ratio": "9:16",
        },
        {
            "scene_index": 2,
            "card_index": 2,
            "scene_id": "scene_2",
            "image_path": panel2,
            "local_path": panel2,
            "video_prompt": "Scene 2: Robot discovers crystalline monument",
            "duration_seconds": 8.0,
            "aspect_ratio": "9:16",
        },
    ]
    return {
        "id": job_id,
        "job_id": job_id,
        "project_id": project_id,
        "user_id": 7126457028,
        "product_type": "storyboard_prompt",
        "engine_route": "storyboard_to_video",
        "engine_adapter": "storyboard_scene_image_video_engine",
        "orchestration_mode": "per_scene_8s",
        "required_capability": "image_to_video",
        "tier_id": tier_id,
        "quality_xu": 371 if tier_id == 400 else 2143,
        "scene_count": 2,
        "scene_duration_seconds": 8,
        "duration_seconds": 16,
        "aspect_ratio": "9:16",
        "scene_cards": cards,
        "storyboard_panels": [
            {"scene_index": 1, "local_path": panel1},
            {"scene_index": 2, "local_path": panel2},
        ],
        "project": {
            "id": project_id,
            "tier_id": tier_id,
            "quoted_price_xu": 371 if tier_id == 400 else 2143,
            "user_id": 7126457028,
            "asset_pack_json": {
                "product_type": "storyboard_prompt",
                "tier_id": tier_id,
                "scene_cards": cards,
            },
        },
    }


def _mock_probe(path, *args, **kwargs):
    d = 16.0 if "final" in str(path) else 8.0
    return {
        "ok": True,
        "duration": d,
        "duration_sec": d,
        "has_video": True,
        "has_audio": True,
        "width": 1080,
        "height": 1920,
    }


class TestStoryboardDualTierRoutingResolution:
    """Proves resolution contract for both Option A (Kling) and Option B (Veo)."""

    def test_tier_400_resolves_shopaikey_veo_fast(self, sample_panels):
        p1, p2 = sample_panels
        job = _build_storyboard_job(p1, p2, tier_id=400)

        # Provider order must resolve to shopaikey_video
        order = _provider_order(job)
        assert order == ["shopaikey_video"], f"Expected ['shopaikey_video'], got {order}"

        # Model must resolve to veo3.1-fast
        model = _resolve_storyboard_i2v_model(job, provider=order[0])
        assert model == "veo3.1-fast", f"Expected 'veo3.1-fast', got {model}"
        assert model in STORYBOARD_PROVEN_I2V_MODELS_BY_PROVIDER["shopaikey_video"]

    def test_tier_800_resolves_key4u_kling_v3(self, sample_panels):
        p1, p2 = sample_panels
        job = _build_storyboard_job(p1, p2, tier_id=800)

        # Provider order must resolve to key4u_video
        order = _provider_order(job)
        assert order == ["key4u_video"], f"Expected ['key4u_video'], got {order}"

        # Model must resolve to kling-v3
        model = _resolve_storyboard_i2v_model(job, provider=order[0])
        assert model == "kling-v3", f"Expected 'kling-v3', got {model}"
        assert model in STORYBOARD_PROVEN_I2V_MODELS_BY_PROVIDER["key4u_video"]

    def test_explicit_model_overrides_work_for_both_tiers(self):
        # Explicit kling model routes to key4u
        job_kling = {
            "product_type": "storyboard_prompt",
            "selected_model": "kling-v3",
        }
        assert _provider_order(job_kling) == ["key4u_video"]
        assert _resolve_storyboard_i2v_model(job_kling, provider="key4u_video") == "kling-v3"

        # Explicit veo3.1-fast routes to shopaikey
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

    def test_dual_tier_economics_from_route_map(self):
        route_map = psg._load_product_video_route_map()
        tiers = route_map.get("tiers_sorted_by_customer_price", [])

        # Tier 400: Veo Fast ($0.70/scene, $1.40 for 2 scenes)
        t400 = next(t for t in tiers if t["tier_id"] == 400)
        c_veo = next(c for c in t400["candidates"] if c["provider"] == "shopaikey")
        assert Decimal(str(c_veo["usd_per_scene"])) == Decimal("0.7")
        assert Decimal(str(c_veo["usd_per_scene"])) * 2 == Decimal("1.4")

        # Tier 800: Kling Pro Audio 10s ($20.40/scene) & Kling 8s ($12.24/scene in tier 400 catalog)
        c_kling_8s = next(c for c in t400["candidates"] if c["provider"] == "key4u" and "kling" in c["model"])
        assert Decimal(str(c_kling_8s["usd_per_scene"])) == Decimal("12.24009792")
        assert Decimal(str(c_kling_8s["usd_per_scene"])) * 2 == Decimal("24.48019584")


class TestStoryboardDualTierRenderProgression:
    """Proves mock render execution on both Tier 400 and Tier 800 with zero real provider calls."""

    def test_tier_400_shopaikey_mock_render_success(self, sample_panels, tmp_path):
        p1, p2 = sample_panels
        job = _build_storyboard_job(p1, p2, tier_id=400, job_id=4401, project_id=4401)
        job["selected_provider"] = "shopaikey_video"
        job["selected_model"] = "veo3.1-fast"
        job["provider_order"] = ["shopaikey_video"]

        sc1_out = str(tmp_path / "scene_01.mp4")
        sc2_out = str(tmp_path / "scene_02.mp4")
        final_mp4 = str(tmp_path / "final_16s.mp4")
        Path(sc1_out).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
        Path(sc2_out).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
        Path(final_mp4).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)

        mock_provider = MagicMock(side_effect=[
            {"ok": True, "output_path": sc1_out, "raw_output_path": sc1_out, "status": "completed", "provider": "shopaikey_video", "model": "veo3.1-fast"},
            {"ok": True, "output_path": sc2_out, "raw_output_path": sc2_out, "status": "completed", "provider": "shopaikey_video", "model": "veo3.1-fast"},
        ])
        mock_finalizer = MagicMock(return_value={
            "ok": True,
            "status": "completed",
            "final_video_path": final_mp4,
            "master_video_path": final_mp4,
            "output_path": final_mp4,
            "final_output_path": final_mp4,
            "duration_sec": 16.0,
        })

        env = {
            "SHOPAIKEY_API_KEY": "test_shopai_key",
            "SHOPAIKEY_VIDEO_ENABLED": "1",
            "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer test_token",
            "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
        }
        render_workspace = str(tmp_path / "work_400")
        with patch.dict(os.environ, env), \
             patch("services.video_real_render_connector.run_provider_generation", mock_provider), \
             patch("services.video_real_render_connector.finalize_multiscene_scene_clips", mock_finalizer), \
             patch("services.multiscene_video_pipeline.finalize_multiscene_scene_clips", mock_finalizer), \
             patch("services.multiscene_video_pipeline.probe_duration", side_effect=lambda p: 16.0 if "final" in str(p) else 8.0), \
             patch("services.multiscene_video_pipeline.probe_media_streams", return_value={"streams": [{"codec_type": "video"}]}), \
             patch("services.video_final_output.probe_video", side_effect=_mock_probe), \
             patch("services.video_local_validation.probe_video_file", side_effect=_mock_probe), \
             patch("services.video_real_render_connector._addon_plan", return_value={}):
            result = render_real_video_job(job, render_workspace)

        assert result.get("ok") is True, f"Render must succeed, got {result}"
        assert mock_provider.call_count == 2, f"Expected 2 scene calls, got {mock_provider.call_count}"
        assert mock_finalizer.call_count == 1, "Finalizer must be called once"

    def test_tier_800_key4u_mock_render_success(self, sample_panels, tmp_path):
        p1, p2 = sample_panels
        job = _build_storyboard_job(p1, p2, tier_id=800, job_id=8801, project_id=8801)
        job["selected_provider"] = "key4u_video"
        job["selected_model"] = "kling-v3"
        job["provider_order"] = ["key4u_video"]

        sc1_out = str(tmp_path / "scene_01.mp4")
        sc2_out = str(tmp_path / "scene_02.mp4")
        final_mp4 = str(tmp_path / "final_16s.mp4")
        Path(sc1_out).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
        Path(sc2_out).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
        Path(final_mp4).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)

        mock_provider = MagicMock(side_effect=[
            {"ok": True, "output_path": sc1_out, "raw_output_path": sc1_out, "status": "completed", "provider": "key4u_video", "model": "kling-v3"},
            {"ok": True, "output_path": sc2_out, "raw_output_path": sc2_out, "status": "completed", "provider": "key4u_video", "model": "kling-v3"},
        ])
        mock_finalizer = MagicMock(return_value={
            "ok": True,
            "status": "completed",
            "final_video_path": final_mp4,
            "master_video_path": final_mp4,
            "output_path": final_mp4,
            "final_output_path": final_mp4,
            "duration_sec": 16.0,
        })

        env = {
            "KEY4U_API_KEY": "test_k4u_sec_key",
            "KEY4U_VIDEO_ENABLED": "1",
            "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test_token",
            "KEY4U_VIDEO_MODEL": "kling-v3",
        }
        render_workspace = str(tmp_path / "work_800")
        with patch.dict(os.environ, env), \
             patch("services.video_real_render_connector.run_provider_generation", mock_provider), \
             patch("services.video_real_render_connector.finalize_multiscene_scene_clips", mock_finalizer), \
             patch("services.multiscene_video_pipeline.finalize_multiscene_scene_clips", mock_finalizer), \
             patch("services.multiscene_video_pipeline.probe_duration", side_effect=lambda p: 16.0 if "final" in str(p) else 8.0), \
             patch("services.multiscene_video_pipeline.probe_media_streams", return_value={"streams": [{"codec_type": "video"}]}), \
             patch("services.video_final_output.probe_video", side_effect=_mock_probe), \
             patch("services.video_local_validation.probe_video_file", side_effect=_mock_probe), \
             patch("services.video_real_render_connector._addon_plan", return_value={}):
            result = render_real_video_job(job, render_workspace)

        assert result.get("ok") is True, f"Render must succeed, got {result}"
        assert mock_provider.call_count == 2, f"Expected 2 scene calls, got {mock_provider.call_count}"
        assert mock_finalizer.call_count == 1, "Finalizer must be called once"

    def test_tier_400_fail_closed_no_fallback_leak(self, sample_panels, tmp_path):
        p1, p2 = sample_panels
        job = _build_storyboard_job(p1, p2, tier_id=400, job_id=4402, project_id=4402)
        job["selected_provider"] = "shopaikey_video"
        job["selected_model"] = "veo3.1-fast"
        job["provider_order"] = ["shopaikey_video"]

        mock_provider = MagicMock(side_effect=RuntimeError("shopaikey_upstream_500"))
        mock_finalizer = MagicMock()

        with patch("services.video_real_render_connector.run_provider_generation", new=mock_provider), \
             patch("services.video_real_render_connector.finalize_multiscene_scene_clips", new=mock_finalizer), \
             patch("services.video_final_output.probe_video", side_effect=_mock_probe):
            try:
                result = render_real_video_job(job, str(tmp_path / "workspace_400_fail"))
            except RealVideoRenderError as exc:
                result = {"ok": False, "error": str(exc), "no_charge": True}

        assert result.get("ok") is False
        assert mock_provider.call_count == 1, f"Expected exactly 1 call, got {mock_provider.call_count}"
        assert mock_finalizer.call_count == 0, "Finalizer must not be called on failure"
        assert job["provider_order"] == ["shopaikey_video"]

    def test_tier_800_fail_closed_no_fallback_leak(self, sample_panels, tmp_path):
        p1, p2 = sample_panels
        job = _build_storyboard_job(p1, p2, tier_id=800, job_id=8802, project_id=8802)
        job["selected_provider"] = "key4u_video"
        job["selected_model"] = "kling-v3"
        job["provider_order"] = ["key4u_video"]

        mock_provider = MagicMock(side_effect=RuntimeError("key4u_upstream_500"))
        mock_finalizer = MagicMock()

        with patch("services.video_real_render_connector.run_provider_generation", new=mock_provider), \
             patch("services.video_real_render_connector.finalize_multiscene_scene_clips", new=mock_finalizer), \
             patch("services.video_final_output.probe_video", side_effect=_mock_probe):
            try:
                result = render_real_video_job(job, str(tmp_path / "workspace_800_fail"))
            except RealVideoRenderError as exc:
                result = {"ok": False, "error": str(exc), "no_charge": True}

        assert result.get("ok") is False
        assert mock_provider.call_count == 1, f"Expected exactly 1 call, got {mock_provider.call_count}"
        assert mock_finalizer.call_count == 0, "Finalizer must not be called on failure"
        assert job["provider_order"] == ["key4u_video"]
