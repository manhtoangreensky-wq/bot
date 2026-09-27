# -*- coding: utf-8 -*-
"""
Tests for P0 Product Video SelfShot ShopAIKey Veo I2V Reference Image Wire Closure (R13.1).
Subtask: FIRST_PARTY_EPHEMERAL_REFERENCE_TRANSPORT_CLOSURE

Invariants:
1. Provider: shopaikey_video
2. Model: veo3.1-fast (family: google_veo)
3. Capability: image_to_video
4. Route: controlled_keyframe_image_to_video
5. Wire contract: metadata.images = ["https://..."]
6. Top-level raw base64 image: FORBIDDEN for Google Veo I2V
7. Local filesystem path on wire: FORBIDDEN
8. Text-to-video fallback: FORBIDDEN
9. Zero live provider calls during tests
"""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from providers import video_generic_http_provider
from providers.video_generic_http_provider import (
    GenericHttpVideoProvider,
    VideoGenerationRequest,
    VideoProviderContractError,
    _shopaikey_wire_payload,
    build_shopaikey_video_payload,
)
from services import video_provider_catalog, video_project_queue, video_tail9


@pytest.fixture
def mock_storage_env(tmp_path):
    storage_dir = tmp_path / "provider_refs"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return {
        "PROVIDER_REFERENCE_STORAGE_DIR": str(storage_dir),
        "PROVIDER_REFERENCE_BASE_URL": "https://toanaas.vn/provider-media/v1",
        "PROVIDER_REFERENCE_TTL_SECONDS": "7200",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
        "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generations",
        "SHOPAIKEY_VIDEO_STATUS_URL": "https://api.shopaikey.com/v1/video/status/{task_id}",
        "SHOPAIKEY_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_API_KEY": "Bearer test_sak_token",
    }


@pytest.fixture
def dummy_keyframe(tmp_path):
    img = tmp_path / "keyframe_scene_01.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00" + b"\x00" * 64)
    return img


# ==============================================================================
# 1. SHOPAIKEY GOOGLE VEO I2V WIRE CONTRACT
# ==============================================================================

def test_shopaikey_veo_i2v_wire_payload_uses_metadata_images(dummy_keyframe, mock_storage_env):
    """Veo I2V wire payload must populate metadata.images and eliminate top-level image."""
    raw_payload = {
        "model": "veo3.1-fast",
        "prompt": "smooth cinematic camera panning",
        "image": str(dummy_keyframe),
        "aspect_ratio": "9:16",
        "duration": 5,
        "metadata": {
            "required_capability": "image_to_video",
            "selected_family": "google_veo",
            "job_id": "job_veo_i2v_001",
        },
    }

    wire = _shopaikey_wire_payload(raw_payload, env=mock_storage_env)

    # 1. Top-level 'image' must be completely removed for Google Veo I2V
    assert "image" not in wire, "Top-level image must be absent for Google Veo I2V"

    # 2. metadata.images must be a list containing the public HTTPS reference URL
    assert "metadata" in wire
    images = wire["metadata"].get("images")
    assert isinstance(images, list)
    assert len(images) == 1
    ref_url = images[0]
    assert ref_url.startswith("https://toanaas.vn/provider-media/v1/")
    assert ref_url.endswith(".jpg")

    # 3. Local filesystem path must never appear anywhere in serialized wire JSON
    wire_json = json.dumps(wire)
    assert str(dummy_keyframe) not in wire_json
    assert "keyframe_scene_01.jpg" not in wire_json
    assert "image_paths" not in wire
    assert "storyboard" not in wire
    assert "source_video_path" not in wire


def test_shopaikey_veo_i2v_existing_https_url_preserved(mock_storage_env):
    """If input image is already a reachable HTTPS URL, it is used directly without materializing."""
    remote_url = "https://cdn.example.com/assets/keyframe_external.jpg"
    raw_payload = {
        "model": "veo3.1-fast",
        "prompt": "cinematic camera movement",
        "image": remote_url,
        "metadata": {
            "required_capability": "image_to_video",
            "selected_family": "google_veo",
        },
    }

    wire = _shopaikey_wire_payload(raw_payload, env=mock_storage_env)
    assert "image" not in wire
    assert wire["metadata"]["images"] == [remote_url]


# ==============================================================================
# 2. MODEL FAMILY ISOLATION: GOOGLE VEO VS OTHER FAMILIES
# ==============================================================================

def test_model_family_isolation_veo_vs_grok(dummy_keyframe, mock_storage_env):
    """Model family isolation: Google Veo uses metadata.images, while Grok retains top-level image."""
    veo_payload = {
        "model": "veo3.1-fast",
        "prompt": "veo shot",
        "image": str(dummy_keyframe),
        "metadata": {"required_capability": "image_to_video", "selected_family": "google_veo"},
    }
    grok_payload = {
        "model": "grok-video-3",
        "prompt": "grok shot",
        "image": str(dummy_keyframe),
        "metadata": {"required_capability": "image_to_video", "selected_family": "xai_grok"},
    }

    veo_wire = _shopaikey_wire_payload(veo_payload, env=mock_storage_env)
    grok_wire = _shopaikey_wire_payload(grok_payload, env=mock_storage_env)

    # Veo: metadata.images present, top-level image absent
    assert "image" not in veo_wire
    assert "images" in veo_wire.get("metadata", {})
    assert veo_wire["metadata"]["images"][0].startswith("https://toanaas.vn/provider-media/v1/")

    # Grok: top-level image present (base64 string), metadata.images absent
    assert "image" in grok_wire
    assert isinstance(grok_wire["image"], str)
    assert "metadata" not in grok_wire or "images" not in grok_wire.get("metadata", {})


# ==============================================================================
# 3. SELFSHOT2 & SELFSHOT3 END-TO-END WIRE INTEGRATION
# ==============================================================================

def test_selfshot2_reference_wire_contract(dummy_keyframe, mock_storage_env):
    """SelfShot2 (self_shot_scene_change) produces metadata.images reference on wire."""
    req = VideoGenerationRequest(
        job_id="job_selfshot2_test",
        product_type="self_shot_scene_change",
        video_flow_type="selfshot2",
        prompt="transform background to mountain vista",
        image_paths=[str(dummy_keyframe)],
        required_capability="image_to_video",
        metadata={
            "product_video": True,
            "required_capability": "image_to_video",
            "selected_provider": "shopaikey_video",
            "selected_model": "veo3.1-fast",
            "selected_family": "google_veo",
            "job_id": "job_selfshot2_test",
        },
    )

    base_payload = build_shopaikey_video_payload(req, env=mock_storage_env)
    wire = _shopaikey_wire_payload(base_payload, env=mock_storage_env)

    assert "image" not in wire
    assert "metadata" in wire and "images" in wire["metadata"]
    assert wire["metadata"]["images"][0].startswith("https://toanaas.vn/provider-media/v1/")
    assert str(dummy_keyframe) not in json.dumps(wire)


def test_selfshot3_reference_wire_contract(dummy_keyframe, mock_storage_env):
    """SelfShot3 (self_shot_cinematic_transform) produces metadata.images reference on wire."""
    req = VideoGenerationRequest(
        job_id="job_selfshot3_test",
        product_type="self_shot_cinematic_transform",
        video_flow_type="selfshot3",
        prompt="dramatic lighting shift and cinematic movement",
        image_paths=[str(dummy_keyframe)],
        required_capability="image_to_video",
        metadata={
            "product_video": True,
            "required_capability": "image_to_video",
            "selected_provider": "shopaikey_video",
            "selected_model": "veo3.1-fast",
            "selected_family": "google_veo",
            "job_id": "job_selfshot3_test",
        },
    )

    base_payload = build_shopaikey_video_payload(req, env=mock_storage_env)
    wire = _shopaikey_wire_payload(base_payload, env=mock_storage_env)

    assert "image" not in wire
    assert "metadata" in wire and "images" in wire["metadata"]
    assert wire["metadata"]["images"][0].startswith("https://toanaas.vn/provider-media/v1/")
    assert str(dummy_keyframe) not in json.dumps(wire)


# ==============================================================================
# 4. FAST-FAIL CLOSED & ZERO PROVIDER CALLS INVARIANTS
# ==============================================================================

def test_missing_image_fails_closed_zero_calls(mock_storage_env):
    """Missing keyframe fails closed before submit with provider_image_input_missing_no_charge."""
    req = VideoGenerationRequest(
        job_id="job_missing_test",
        product_type="self_shot_scene_change",
        required_capability="image_to_video",
        prompt="cinematic camera movement",
        image_paths=[],
        metadata={
            "required_capability": "image_to_video",
            "selected_model": "veo3.1-fast",
        },
    )

    adapter = GenericHttpVideoProvider(
        provider_name="shopaikey_video",
        enabled_env="SHOPAIKEY_VIDEO_ENABLED",
        submit_url_env="SHOPAIKEY_VIDEO_SUBMIT_URL",
        poll_url_env="SHOPAIKEY_VIDEO_STATUS_URL",
        auth_header_name_env="SHOPAIKEY_AUTH_HEADER_NAME",
        auth_header_value_env="SHOPAIKEY_API_KEY",
        model_env="SHOPAIKEY_VIDEO_MODEL",
        env=mock_storage_env,
    )

    with patch("urllib.request.urlopen") as spy_urlopen:
        res = adapter.submit_video_job(req)
        assert res.ok is False
        assert res.error_code == "provider_image_input_missing_no_charge"
        assert res.raw.get("no_charge") is True
        assert spy_urlopen.call_count == 0, "Zero provider calls on contract validation failure"


def test_invalid_image_fails_closed_zero_calls(tmp_path, mock_storage_env):
    """Corrupted/non-existent image file fails closed with shopaikey_veo_i2v_public_reference_unavailable_no_charge."""
    nonexistent = tmp_path / "does_not_exist.jpg"
    payload = {
        "model": "veo3.1-fast",
        "prompt": "cinematic shot",
        "image": str(nonexistent),
        "metadata": {
            "required_capability": "image_to_video",
            "selected_family": "google_veo",
        },
    }

    with pytest.raises(VideoProviderContractError) as exc_info:
        _shopaikey_wire_payload(payload, env=mock_storage_env)
    assert exc_info.value.blocker in (
        "provider_image_input_missing_or_invalid",
        "shopaikey_veo_i2v_public_reference_unavailable_no_charge",
    )
    assert exc_info.value.debug.get("no_charge") is True
