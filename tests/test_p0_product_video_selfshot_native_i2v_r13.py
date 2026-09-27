# -*- coding: utf-8 -*-
"""
Tests for P0 Product Video SelfShot Native Image-to-Video Architecture Closure (R13).

Strict Invariants:
1. Public product IDs preserved: self_shot_scene_change, self_shot_cinematic_transform
2. Engine route: controlled_keyframe_image_to_video
3. Required capability: image_to_video
4. Fal is 100% unreachable (FAL_PROVIDER_ELIGIBLE=NO)
5. Approved native providers:
   - key4u_video (kling-v3, grok-imagine-video)
   - shopaikey_video (veo3.1-fast)
6. Source video local reference only (never sent on wire)
7. Fresh legacy V2V fails closed: selfshot_legacy_v2v_route_forbidden_no_charge
8. No text-to-video fallback allowed
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock

from services import video_tail9, video_final_output, video_project_queue, video_provider_catalog
from services import video_real_render_connector
from services.video_real_render_connector import RealVideoRenderError
from providers import video_generic_http_provider


# ==============================================================================
# FIRST RED MATRIX: Proves defects exist prior to source modification
# ==============================================================================

def test_first_red_a1_selfshot2_public_queue_contract_persists_i2v():
    """FIRST RED A1: SelfShot2 public queue contract must persist controlled_keyframe_image_to_video / image_to_video."""
    contract = video_project_queue.product_video_engine_contract("self_shot_scene_change")
    assert contract["engine_route"] == "controlled_keyframe_image_to_video"
    assert contract["required_capability"] == "image_to_video"
    assert contract["package_capability"] == "image_to_video"

    comm = video_tail9.commercial_contract("self_shot_scene_change")
    assert comm["engine_route"] == "controlled_keyframe_image_to_video"
    assert comm["required_capability"] == "image_to_video"

    route = video_final_output.route_for_product_type("self_shot_scene_change")
    assert route["provider_capability"] == "image_to_video"
    assert route["engine_adapter"] == "controlled_keyframe_image_to_video"


def test_first_red_a2_selfshot3_public_queue_contract_persists_i2v():
    """FIRST RED A2: SelfShot3 public queue contract must persist controlled_keyframe_image_to_video / image_to_video."""
    contract = video_project_queue.product_video_engine_contract("self_shot_cinematic_transform")
    assert contract["engine_route"] == "controlled_keyframe_image_to_video"
    assert contract["required_capability"] == "image_to_video"
    assert contract["package_capability"] == "image_to_video"

    comm = video_tail9.commercial_contract("self_shot_cinematic_transform")
    assert comm["engine_route"] == "controlled_keyframe_image_to_video"
    assert comm["required_capability"] == "image_to_video"

    route = video_final_output.route_for_product_type("self_shot_cinematic_transform")
    assert route["provider_capability"] == "image_to_video"
    assert route["engine_adapter"] == "controlled_keyframe_image_to_video"


def test_first_red_b1_shopaikey_selfshot_i2v_payload_contract(tmp_path):
    """FIRST RED B1: ShopAIKey veo3.1-fast must support image_to_video capability and payload serialization without path leak."""
    model_cfg = video_provider_catalog.provider_model_config("shopaikey_video", "veo3.1-fast")
    assert model_cfg is not None, "shopaikey_video veo3.1-fast must exist in catalog"
    caps = model_cfg.get("capabilities", [])
    assert "image_to_video" in caps, "veo3.1-fast must support image_to_video"

    # Field validation for image_to_video
    payload_contract = video_provider_catalog.payload_contract_for_model("shopaikey_video", "veo3.1-fast")
    assert "image" in payload_contract.get("allowed_fields", [])
    assert "image_paths" in payload_contract.get("allowed_fields", [])
    by_cap = payload_contract.get("allowed_fields_by_capability", {})
    assert "image" in by_cap.get("image_to_video", [])
    assert "image_paths" in by_cap.get("image_to_video", [])

    # Test wire payload serialization: local image converted to base64, raw paths popped
    dummy_img = tmp_path / "keyframe.jpg"
    dummy_img.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32)

    raw_payload = {
        "model": "veo3.1-fast",
        "prompt": "smooth cinematic motion",
        "image": str(dummy_img),
        "image_paths": [str(dummy_img)],
        "storyboard": [str(dummy_img)],
        "aspect_ratio": "9:16",
        "duration": 8,
    }
    wire = video_generic_http_provider._shopaikey_wire_payload(raw_payload)
    assert wire["image"].startswith("data:image/jpeg;base64,") or len(wire["image"]) > 30
    assert not os.path.exists(wire["image"])
    assert "image_paths" not in wire
    assert "storyboard" not in wire


def test_first_red_b2_selfshot_i2v_model_resolver_is_provider_aware():
    """FIRST RED B2: Shared SelfShot I2V resolver must be provider-aware and validate allowed models per provider."""
    environ = {
        "KEY4U_API_KEY": "test_k4u",
        "KEY4U_KLING_VIDEO_ENDPOINT": "https://api.key4u.vn/kling/v1/videos/image2video",
        "SHOPAIKEY_API_KEY": "test_sak",
        "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com",
    }
    # ShopAIKey provider-aware resolution
    model, family = video_real_render_connector._resolve_selfshot_i2v_model(
        job={"selected_model": "veo3.1-fast"},
        asset_pack={},
        environ=environ,
        provider="shopaikey_video",
    )
    assert model == "veo3.1-fast"
    assert family == "google_veo"

    # Key4U provider-aware resolution
    model_k4u, family_k4u = video_real_render_connector._resolve_selfshot_i2v_model(
        job={"selected_model": "kling-v3"},
        asset_pack={},
        environ=environ,
        provider="key4u_video",
    )
    assert model_k4u == "kling-v3"
    assert family_k4u == "kling"

    # Reject cross-provider model
    with pytest.raises(RealVideoRenderError) as exc_info:
        video_real_render_connector._resolve_selfshot_i2v_model(
            job={"selected_model": "kling-v3"},
            asset_pack={},
            environ=environ,
            provider="shopaikey_video",
        )
    assert "selfshot_i2v_model_not_proven_no_charge" in str(exc_info.value)


def test_first_red_c1_fal_unreachable_and_legacy_v2v_forbidden(tmp_path):
    """FIRST RED C1: Fal must be unreachable even under selfshot2, and fresh legacy V2V must fail-closed."""
    fake_environ = {
        "FAL_KEY": "test_fal_key",
        "KEY4U_API_KEY": "test_key4u_key",
        "SHOPAIKEY_API_KEY": "test_shopaikey_key",
    }
    with patch.dict(os.environ, fake_environ, clear=False):
        configs = video_real_render_connector._resolve_v2v_provider_configs(
            flow="selfshot2",
            provider_order=["fal_video", "key4u_video", "shopaikey_video"],
            duration_seconds=5,
        )
        provider_names = [c.provider_name for c in configs]
        assert "fal_video" not in provider_names, f"Fal must NEVER be eligible: {provider_names}"
        assert "fal.ai" not in provider_names

    # Fresh legacy V2V must fail closed without charge
    dummy_video = tmp_path / "source.mp4"
    dummy_video.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64)

    fresh_job = {
        "job_id": "test_fresh_legacy",
        "source_video_local_path": str(dummy_video),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "quality_tier": 500,
        "route": "video_to_video",  # Legacy route
        "required_capability": "video_to_video",
    }
    fresh_asset_pack = {
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "quality_tier": 500,
        "source_segment": {"start_seconds": 0.0, "duration_seconds": 5.0},
    }

    with pytest.raises(RealVideoRenderError) as exc_info2:
        video_real_render_connector._render_selfshot2_video_to_video(
            job=fresh_job,
            asset_pack=fresh_asset_pack,
            raw_path=str(tmp_path / "out2.mp4"),
            fallback_prompt="test",
            aspect_ratio="9:16",
            scene_index=0,
        )
    assert "selfshot_legacy_v2v_route_forbidden_no_charge" in str(exc_info2.value)

    with pytest.raises(RealVideoRenderError) as exc_info3:
        video_real_render_connector._render_selfshot3_video_to_video(
            job=fresh_job,
            asset_pack=fresh_asset_pack,
            raw_path=str(tmp_path / "out3.mp4"),
            fallback_prompt="test",
            aspect_ratio="9:16",
        )
    assert "selfshot_legacy_v2v_route_forbidden_no_charge" in str(exc_info3.value)


# ==============================================================================
# ADDITIONAL INVARIANT VERIFICATIONS: Native I2V continuity & wire safety
# ==============================================================================

def test_source_video_never_sent_on_wire_in_controlled_keyframe(tmp_path):
    """Invariant: Source video is local reference only; never present in wire payload."""
    dummy_img = tmp_path / "keyframe.png"
    dummy_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    dummy_video = tmp_path / "source.mp4"
    dummy_video.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 32)

    # When building payload for shopaikey or key4u, source_video_path must not be sent on wire
    payload = {
        "model": "veo3.1-fast",
        "prompt": "transform scene",
        "image": str(dummy_img),
        "source_video_path": str(dummy_video),
        "aspect_ratio": "9:16",
        "duration": 8,
    }
    wire = video_generic_http_provider._shopaikey_wire_payload(payload)
    assert "source_video_path" not in wire
    assert str(dummy_video) not in json.dumps(wire)


def test_selfshot_text_to_video_fallback_forbidden():
    """Invariant: Text-to-video fallback is strictly forbidden for SelfShot2/3."""
    comm2 = video_tail9.commercial_contract("self_shot_scene_change")
    comm3 = video_tail9.commercial_contract("self_shot_cinematic_transform")

    assert "text_to_video" not in comm2.get("fallback_capabilities", ())
    assert "text_to_video" not in comm3.get("fallback_capabilities", ())
    assert comm2.get("required_capability") != "text_to_video"
    assert comm3.get("required_capability") != "text_to_video"
