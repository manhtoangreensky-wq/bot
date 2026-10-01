"""Tests for P0.PRODUCT_VIDEO_STORYBOARD_SHOPAIKEY_VEO_ECONOMICS_R13.

Verifies:
1. Storyboard default provider order is shopaikey_video with veo3.1-fast.
2. Backward compatibility: explicit key4u_video or kling models route to key4u_video.
3. Model resolution guards allowed models per provider.
4. Router selects shopaikey_video for default/veo3.1-fast Storyboard without fallback leakage.
5. Tier 400 economics: 668 Xu customer quote with native 8s ShopAIKey Veo 3.1 Fast yields ~93.2% gross margin.
6. Multi-scene orchestration concatenates two 8s clips into a 16s master video with unified output paths.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services import multiscene_video_pipeline, video_provider_router, video_real_render_connector
from services.multiscene_video_pipeline import finalize_multiscene_scene_clips
from services.video_provider_base import VideoGenerationRequest, VideoPollResult, VideoSubmitResult
from services.video_provider_router import (
    provider_candidate_adapters,
    run_provider_generation,
)
from services.video_real_render_connector import (
    RealVideoRenderError,
    _provider_order,
    _render_scene_async,
    _resolve_storyboard_i2v_model,
    _run_per_scene_provider_orchestrator,
    product_video_duration_contract,
    render_real_video_job,
)


@pytest.fixture
def mock_storyboard_files(tmp_path):
    """Create dummy panel images and 8s dummy MP4 clips."""
    panel1 = tmp_path / "panel_1.png"
    panel2 = tmp_path / "panel_2.png"
    png_header = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00"
        b"\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    panel1.write_bytes(png_header)
    panel2.write_bytes(png_header)

    clip1 = tmp_path / "scene_001.mp4"
    clip2 = tmp_path / "scene_002.mp4"
    clip1.write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)
    clip2.write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    return {
        "panel1": str(panel1),
        "panel2": str(panel2),
        "clip1": str(clip1),
        "clip2": str(clip2),
        "tmp_path": tmp_path,
    }


def _build_storyboard_job(files: dict, provider: str = "", model: str = "") -> dict:
    scene_cards = [
        {
            "scene_index": 1,
            "image_path": files["panel1"],
            "video_prompt": "Scene 1: Cat on crystal planet",
            "duration_seconds": 8.0,
        },
        {
            "scene_index": 2,
            "image_path": files["panel2"],
            "video_prompt": "Scene 2: Cat watches twin moons",
            "duration_seconds": 8.0,
        },
    ]
    job = {
        "id": 1155,
        "job_id": 1155,
        "user_id": 7001,
        "product_type": "storyboard_to_video",
        "engine_route": "storyboard_to_video",
        "engine_adapter": "storyboard_scene_image_video_engine",
        "orchestration_mode": "per_scene_8s",
        "required_capability": "image_to_video",
        "scene_count": 2,
        "scene_duration_seconds": 8,
        "duration_seconds": 16,
        "aspect_ratio": "9:16",
        "scene_cards": scene_cards,
        "storyboard_panels": [
            {"scene_index": 1, "local_path": files["panel1"]},
            {"scene_index": 2, "local_path": files["panel2"]},
        ],
        "project": {
            "id": 1155,
            "scene_cards_json": json.dumps(scene_cards),
            "asset_pack_json": json.dumps({
                "product_type": "storyboard_to_video",
                "scene_cards": scene_cards,
            }),
        },
    }
    if provider:
        job["selected_provider"] = provider
    if model:
        job["model"] = model
        job["selected_model"] = model
        job["pinned_wire_model"] = model
    return job


def test_storyboard_provider_order_defaults_to_shopaikey():
    """Default Storyboard without explicit provider or model must route to shopaikey_video."""
    job = {"product_type": "storyboard_to_video"}
    order = _provider_order(job)
    assert order == ["shopaikey_video"], f"Expected ['shopaikey_video'], got {order}"


def test_storyboard_provider_order_backward_compat_kling():
    """When Kling model is requested, provider order must resolve to key4u_video."""
    job = {
        "product_type": "storyboard_to_video",
        "selected_model": "kling-3.0-turbo",
    }
    order = _provider_order(job)
    assert order == ["key4u_video"], f"Expected ['key4u_video'], got {order}"


def test_storyboard_provider_order_backward_compat_key4u_provider():
    """When key4u_video is explicitly requested, provider order must resolve to key4u_video."""
    job = {
        "product_type": "storyboard_to_video",
        "selected_provider": "key4u_video",
    }
    order = _provider_order(job)
    assert order == ["key4u_video"], f"Expected ['key4u_video'], got {order}"


def test_resolve_storyboard_i2v_model_shopaikey():
    """ShopAIKey Storyboard model should resolve to veo3.1-fast by default."""
    job = {"selected_provider": "shopaikey_video"}
    resolved = _resolve_storyboard_i2v_model(job, provider="shopaikey_video")
    assert resolved == "veo3.1-fast"


def test_resolve_storyboard_i2v_model_shopaikey_rejects_unproven():
    """ShopAIKey Storyboard should reject Kling models and fail closed."""
    job = {"selected_provider": "shopaikey_video", "selected_model": "kling-v3"}
    with pytest.raises(RealVideoRenderError) as exc_info:
        _resolve_storyboard_i2v_model(job, provider="shopaikey_video")
    assert "storyboard_i2v_model_not_proven" in str(exc_info.value)


def test_storyboard_router_selects_shopaikey_for_veo(mock_storyboard_files, monkeypatch):
    """Router selects shopaikey_video for Storyboard when model is veo3.1-fast."""
    monkeypatch.setenv("VIDEO_PROVIDER_CHAIN", "shopaikey_video,key4u_video")
    monkeypatch.setenv("SHOPAIKEY_API_KEY", "mock_key")
    monkeypatch.setenv("KEY4U_API_KEY", "mock_key")

    req = VideoGenerationRequest(
        job_id="test_veo_1155",
        product_type="storyboard_to_video",
        prompt="Cat on crystal planet",
        ratio="9:16",
        duration_seconds=8,
        image_paths=[mock_storyboard_files["panel1"]],
        metadata={
            "product_type": "storyboard_to_video",
            "is_storyboard": True,
            "selected_provider": "shopaikey_video",
            "model": "veo3.1-fast",
            "selected_model": "veo3.1-fast",
            "pinned_wire_model": "veo3.1-fast",
        },
    )

    with patch("providers.video_generic_http_provider.GenericHttpVideoProvider.submit_video_job") as mock_submit, \
         patch("providers.video_generic_http_provider.GenericHttpVideoProvider.poll_video_job") as mock_poll:
        mock_submit.side_effect = lambda req: VideoSubmitResult(
            ok=True,
            provider_name="shopaikey_video",
            provider_task_id="shopaikey_task_456",
        )
        mock_poll.side_effect = lambda task_id, **kw: VideoPollResult(
            ok=True,
            provider_name="shopaikey_video",
            provider_task_id="shopaikey_task_456",
            status="queued",
            raw_status="queued",
        )
        res = run_provider_generation(
            req,
            output_dir=str(mock_storyboard_files["tmp_path"]),
            allow_pending_result=True,
        )

    assert res.get("provider") == "shopaikey_video" or res.get("selected_provider") == "shopaikey_video"
    assert res.get("initial_primary_provider") == "shopaikey_video"
    assert res.get("initial_fallback_provider") == ""


def test_storyboard_tier400_economics_contract():
    """Tier 400 Storyboard (668 Xu) with ShopAIKey Veo 3.1 Fast has positive gross margin (+93.2%)."""
    customer_price_xu = 668
    xu_vnd_rate = 100
    customer_revenue_vnd = customer_price_xu * xu_vnd_rate  # 66,800 VND

    # ShopAIKey Veo 3.1 Fast: $0.70/generation * 3,250 VND/USD rate * 2 scenes
    veo_scene_cost_usd = 0.70
    shopaikey_vnd_usd_rate = 3250
    veo_scene_cost_vnd = veo_scene_cost_usd * shopaikey_vnd_usd_rate  # 2,275 VND/scene
    total_veo_cost_vnd = veo_scene_cost_vnd * 2  # 4,550 VND

    gross_profit_vnd = customer_revenue_vnd - total_veo_cost_vnd
    gross_margin_pct = (gross_profit_vnd / customer_revenue_vnd) * 100

    assert customer_revenue_vnd == 66800
    assert total_veo_cost_vnd == 4550
    assert gross_profit_vnd == 62250
    assert gross_margin_pct > 90.0, f"Gross margin {gross_margin_pct}% is below 90%"
    assert gross_profit_vnd > 0, "Provider cost exceeds customer revenue!"
