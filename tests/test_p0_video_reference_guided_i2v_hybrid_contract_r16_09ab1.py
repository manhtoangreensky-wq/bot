"""Comprehensive contract and regression tests for reference-guided I2V hybrid route.

Task ID: P0.PRODUCT_VIDEO_VIDEO_AI_VIDEO_REFERENCE_REFERENCE_GUIDED_I2V_HYBRID_REMEDIATION_R16_09AB1
Product: video_ai_video_reference
Execution Mode: video_reference_guided_i2v
Source Input Kind: video
Provider Capability: image_to_video
Primary: shopaikey_video / veo3.1-fast
Secondary: key4u_video / veo3.1-components (unpriced / fail-closed)
Strict zero-real-call policy: 100% provider-free / mock transport.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from services.video_reference_package import (
    validate_source_video,
    probe_video_duration,
    extract_deterministic_reference_frames,
    build_reference_prompt_context,
    create_video_reference_package,
    compute_file_sha256,
    VideoReferenceValidationError,
    VideoReferenceExtractionError,
)
from providers.video_generic_http_provider import (
    _shopaikey_wire_payload,
    _key4u_wire_payload,
    build_shopaikey_video_payload,
    build_key4u_video_payload,
    VideoProviderContractError,
)
from services.video_provider_base import VideoGenerationRequest
from services import video_ai_edit_provider
from services import video_ai_real_pricing
from services import video_provider_catalog
from services import web_product_video_worker_consumer


@pytest.fixture
def mock_storage_root(tmp_path: Path, monkeypatch) -> Path:
    storage = tmp_path / "provider_refs"
    storage.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROVIDER_REFERENCE_STORAGE_DIR", str(storage))
    monkeypatch.setenv("PROVIDER_REFERENCE_BASE_URL", "https://toanaas.vn/provider-media/v1")
    return storage


@pytest.fixture
def sample_source_video(tmp_path: Path) -> Path:
    video_path = tmp_path / "reference_source.mp4"
    video_path.write_bytes(b"MOCK_MP4_SAMPLE_DATA_FOR_HYBRID_TEST_0123456789")
    return video_path


# ---------------------------------------------------------------------------
# 1. Source Video Validation & Error Contracts
# ---------------------------------------------------------------------------

def test_source_video_validation_success(sample_source_video: Path):
    """Valid video file returns authoritative metadata with SHA256 and duration."""
    meta = validate_source_video(sample_source_video, fallback_duration=5.0)
    assert meta["ok"] is True
    assert meta["source_video_name"] == "reference_source.mp4"
    assert meta["extension"] == ".mp4"
    assert meta["file_size"] > 0
    assert meta["duration_seconds"] == 5.0
    expected_sha = hashlib.sha256(sample_source_video.read_bytes()).hexdigest()
    assert meta["source_video_sha256"] == expected_sha


def test_source_video_validation_missing_path():
    """Missing or empty source video path fails validation."""
    with pytest.raises(VideoReferenceValidationError) as exc:
        validate_source_video("")
    assert "MISSING_SOURCE_VIDEO_PATH" in str(exc.value)


def test_source_video_validation_nonexistent_file(tmp_path: Path):
    """Non-existent video file fails validation."""
    absent = tmp_path / "nonexistent.mp4"
    with pytest.raises(VideoReferenceValidationError) as exc:
        validate_source_video(absent)
    assert "SOURCE_VIDEO_NOT_FOUND" in str(exc.value)


def test_source_video_validation_unsupported_extension(tmp_path: Path):
    """Unsupported file extension fails validation."""
    bad_file = tmp_path / "source.txt"
    bad_file.write_text("not a video")
    with pytest.raises(VideoReferenceValidationError) as exc:
        validate_source_video(bad_file)
    assert "INVALID_VIDEO_EXTENSION" in str(exc.value)


def test_source_video_validation_empty_file(tmp_path: Path):
    """Empty (zero byte) video file fails validation."""
    empty_file = tmp_path / "empty.mp4"
    empty_file.write_bytes(b"")
    with pytest.raises(VideoReferenceValidationError) as exc:
        validate_source_video(empty_file)
    assert "SOURCE_VIDEO_EMPTY" in str(exc.value)


# ---------------------------------------------------------------------------
# 2. Deterministic 2-Frame Extraction Contract
# ---------------------------------------------------------------------------

def test_extract_deterministic_two_frames(sample_source_video: Path, tmp_path: Path):
    """Extracts exactly 2 reference frames: start frame (0.0s) and end frame (duration-0.1s)."""
    out_dir = tmp_path / "extracted_frames"
    frames = extract_deterministic_reference_frames(
        sample_source_video,
        output_dir=out_dir,
        duration=6.0,
        fallback_on_ffmpeg_error=True,
    )
    assert len(frames) == 2

    # Frame 1: start frame at 0.0s
    f1 = frames[0]
    assert f1["frame_index"] == 1
    assert f1["role"] == "start_frame"
    assert f1["timestamp_seconds"] == 0.0
    assert Path(f1["frame_path"]).exists()
    assert f1["file_size"] > 0
    assert len(f1["frame_sha256"]) == 64

    # Frame 2: end frame at 5.9s (max(0.1, 6.0 - 0.1))
    f2 = frames[1]
    assert f2["frame_index"] == 2
    assert f2["role"] == "end_frame"
    assert f2["timestamp_seconds"] == 5.9
    assert Path(f2["frame_path"]).exists()
    assert f2["file_size"] > 0
    assert len(f2["frame_sha256"]) == 64

    # Frames must have distinct, deterministic SHA256 digests
    assert f1["frame_sha256"] != f2["frame_sha256"]


# ---------------------------------------------------------------------------
# 3. Prompt Authority & Package Assembly
# ---------------------------------------------------------------------------

def test_build_reference_prompt_context():
    """Preserves user prompt authority and generates deterministic prompt SHA256."""
    prompt = "Cinematic slow motion drone shot of a misty pine forest"
    effective_prompt, prompt_sha = build_reference_prompt_context(prompt)
    assert effective_prompt == prompt
    assert prompt_sha == hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def test_create_video_reference_package(sample_source_video: Path, tmp_path: Path):
    """create_video_reference_package builds complete authoritative package."""
    prompt = "Transform camera movement smoothly"
    pkg = create_video_reference_package(
        sample_source_video,
        user_prompt=prompt,
        output_dir=tmp_path / "pkg_frames",
        duration=5.0,
    )
    assert pkg["execution_mode"] == "video_reference_guided_i2v"
    assert pkg["source_input_kind"] == "video"
    assert pkg["source_video_path"] == str(sample_source_video.resolve())
    assert pkg["duration_seconds"] == 5.0
    assert pkg["frame_count"] == 2
    assert len(pkg["frame_paths"]) == 2
    assert pkg["user_prompt"] == prompt
    assert pkg["native_v2v"] is False
    assert pkg["native_v2v_enabled"] is False


# ---------------------------------------------------------------------------
# 4. Primary Wire Contract: ShopAIKey Veo 3.1 Fast (metadata.images)
# ---------------------------------------------------------------------------

def test_shopaikey_wire_payload_multi_frame_reference_urls(mock_storage_root: Path, sample_source_video: Path, tmp_path: Path):
    """_shopaikey_wire_payload populates metadata.images = [url1, url2] and purges local paths."""
    frames = extract_deterministic_reference_frames(
        sample_source_video,
        output_dir=tmp_path / "sh_frames",
        duration=5.0,
    )
    frame_paths = [f["frame_path"] for f in frames]

    raw_payload = {
        "model": "veo3.1-fast",
        "prompt": "Reference guided video transformation",
        "aspect_ratio": "9:16",
        "capability": "image_to_video",
        "required_capability": "image_to_video",
        "image_paths": frame_paths,
        "source_video_path": str(sample_source_video),
        "metadata": {
            "selected_family": "google_veo",
            "required_capability": "image_to_video",
            "source_video_path": str(sample_source_video),
            "video_path": str(sample_source_video),
        },
    }

    env = {
        "PROVIDER_REFERENCE_STORAGE_DIR": str(mock_storage_root),
        "PROVIDER_REFERENCE_BASE_URL": "https://toanaas.vn/provider-media/v1",
    }

    wire = _shopaikey_wire_payload(raw_payload, env=env)

    # 1. Images field on metadata must have exactly 2 valid HTTPS URLs
    meta = wire["metadata"]
    assert "images" in meta
    assert isinstance(meta["images"], list)
    assert len(meta["images"]) == 2
    for url in meta["images"]:
        assert url.startswith("https://toanaas.vn/provider-media/v1/")
        assert url.endswith(".jpg")

    assert meta["provider_reference_present"] is True
    assert meta["provider_reference_count"] == 2
    assert meta["provider_reference_host"] == "toanaas.vn"

    # 2. External wire safety: zero raw local MP4 or VPS filesystem path on wire
    assert "source_video_path" not in wire
    assert "video_path" not in wire
    assert "image_paths" not in wire
    assert "image" not in wire
    assert "source_video_path" not in meta
    assert "video_path" not in meta


# ---------------------------------------------------------------------------
# 5. Secondary Wire Contract: Key4U Veo 3.1 Components (wire.images)
# ---------------------------------------------------------------------------

def test_key4u_wire_payload_multi_frame_reference_urls(mock_storage_root: Path, sample_source_video: Path, tmp_path: Path):
    """_key4u_wire_payload populates wire.images = [url1, url2] and purges local paths."""
    frames = extract_deterministic_reference_frames(
        sample_source_video,
        output_dir=tmp_path / "k4u_frames",
        duration=5.0,
    )
    frame_paths = [f["frame_path"] for f in frames]

    raw_payload = {
        "model": "veo3.1-components",
        "prompt": "Secondary reference guided transformation",
        "aspect_ratio": "9:16",
        "image_paths": frame_paths,
        "source_video_path": str(sample_source_video),
        "metadata": {
            "selected_family": "google_veo",
            "source_video_path": str(sample_source_video),
        },
    }

    env = {
        "KEY4U_BASE_URL": "https://api.key4u.vn",
        "PROVIDER_REFERENCE_STORAGE_DIR": str(mock_storage_root),
        "PROVIDER_REFERENCE_BASE_URL": "https://toanaas.vn/provider-media/v1",
    }

    wire = _key4u_wire_payload(raw_payload, submit_url="https://api.key4u.vn/v1/videos", env=env)

    # 1. Images field on top-level wire must have exactly 2 valid HTTPS URLs
    assert "images" in wire
    assert isinstance(wire["images"], list)
    assert len(wire["images"]) == 2
    for url in wire["images"]:
        assert url.startswith("https://toanaas.vn/provider-media/v1/")
        assert url.endswith(".jpg")

    # 2. External wire safety: zero raw local MP4 or VPS filesystem path on wire
    assert "source_video_path" not in wire
    assert "video_path" not in wire
    assert "image_paths" not in wire
    out_meta = wire.get("metadata") or {}
    assert "source_video_path" not in out_meta
    assert "video_path" not in out_meta


# ---------------------------------------------------------------------------
# 6. Negative Wire & Guard Invariants
# ---------------------------------------------------------------------------

def test_native_v2v_contracts_remain_fail_closed():
    """Native V2V wire contracts remain False for both shopaikey_video and key4u_video."""
    assert video_ai_edit_provider.has_proven_v2v_wire_contract("shopaikey_video") is False
    assert video_ai_edit_provider.has_proven_v2v_wire_contract("key4u_video") is False
    assert video_ai_edit_provider.has_proven_v2v_wire_contract("toanaas_video") is False


def test_key4u_veo_legacy_create_rejected_no_charge():
    """Key4U Veo legacy endpoint /v1/video/create is fail-closed."""
    payload = {
        "prompt": "Test legacy create rejection",
        "metadata": {
            "selected_family": "google_veo",
        },
    }
    with pytest.raises(VideoProviderContractError) as exc_info:
        _key4u_wire_payload(payload, submit_url="https://api.key4u.vn/v1/video/create")
    assert exc_info.value.blocker == "key4u_veo_legacy_create_rejected_no_charge"
    assert exc_info.value.debug["no_charge"] is True


# ---------------------------------------------------------------------------
# 7. Pricing Authority Gate
# ---------------------------------------------------------------------------

def test_pricing_authority_gate_primary_approved_secondary_fail_closed():
    """ShopAIKey Veo 3.1 fast is canonically priced; Key4U veo3.1-components is unpriced/fail-closed."""
    # Primary: ShopAIKey veo3.1-fast is canonically priced at $0.700 USD/scene
    found_shopaikey = False
    for catalog_entry in video_ai_real_pricing._MODEL_ROWS:
        prov = catalog_entry.get("providers", {}).get("shopaikey", {})
        if prov.get("model") == "veo3.1-fast":
            assert prov.get("usd_per_scene") == "0.700"
            found_shopaikey = True
            break
    assert found_shopaikey is True

    # Secondary: Key4U veo3.1-components is NOT priced in canonical catalog -> fails closed
    key4u_priced = False
    for catalog_entry in video_ai_real_pricing._MODEL_ROWS:
        prov = catalog_entry.get("providers", {}).get("key4u", {})
        if prov.get("model") == "veo3.1-components":
            key4u_priced = True
            break
    assert key4u_priced is False


# ---------------------------------------------------------------------------
# 8. Consumer Envelope Mapping & Route Binding
# ---------------------------------------------------------------------------

def test_map_web_job_to_bot_runtime_video_ai_video_reference(sample_source_video: Path, mock_storage_root: Path):
    """Consumer maps video_ai_video_reference job into I2V hybrid route with extracted frames."""
    job = {
        "job_id": "pvj_ref_hybrid_001",
        "request_id": "VID-20261003-HYBRID01",
        "account_id": "acc_test_owner",
        "product_key": "video_ai_video_reference",
        "status": "processing",
        "payload": {
            "source_video_path": str(sample_source_video),
            "prompt": "Stunning transition of scenic mountain landscape",
            "aspect_ratio": "9:16",
            "duration": 5,
            "quality_tier": "standard",
        },
    }

    runtime_sha = "c8b0835b04afa617a7a5fd829bce17efebec15ea"
    auth = {
        "job_id": "pvj_ref_hybrid_001",
        "owner_authorized": True,
        "product_type": "video_ai_video_reference",
        "provider": "shopaikey_video",
        "model": "veo3.1-fast",
        "capability": "image_to_video",
        "acceptance_type": "owner_authorized_live_acceptance_lane",
        "user_id": "acc_test_owner",
        "tier": "400",
        "runtime_sha": runtime_sha,
        "max_provider_spend": 1.00,
        "max_provider_spend_unit": "USD",
        "nonce": "nonce_test_ref_001",
        "consumed": False,
        "expires_at": 2000000000.0,
    }

    env = {
        "PROVIDER_REFERENCE_STORAGE_DIR": str(mock_storage_root),
        "PROVIDER_REFERENCE_BASE_URL": "https://toanaas.vn/provider-media/v1",
        "DEPLOYED_GIT_SHA": runtime_sha,
    }

    req = web_product_video_worker_consumer.map_web_job_to_bot_runtime(
        job,
        owner_acceptance_auth=auth,
        environ=env,
    )

    assert req.job_id == "pvj_ref_hybrid_001"
    assert req.product_type == "video_ai_video_reference"
    assert req.video_flow_type == "video_ai_video_reference"
    assert req.required_capability == "image_to_video"
    assert len(req.image_paths) == 2
    assert req.metadata["execution_mode"] == "video_reference_guided_i2v"
    assert req.metadata["source_input_kind"] == "video"
    assert req.metadata["native_v2v"] is False
    assert req.metadata["native_v2v_enabled"] is False
    assert "prompt_sha256" in req.metadata
    assert "source_video_sha256" in req.metadata


def test_routing_config_authoritative_contract():
    """config/product_video_model_routing.json has exact reference-guided I2V hybrid schema."""
    routing = video_provider_catalog.load_product_video_model_routing()
    assert "fal_video" in routing["default_provider_chain"]
    assert "product_routes" in routing
    prod_route = routing["product_routes"].get("video_ai_video_reference")
    assert prod_route is not None
    assert prod_route["product"] == "video_ai_video_reference"
    assert prod_route["execution_mode"] == "video_reference_guided_i2v"
    assert prod_route["source_input"] == "video"
    assert prod_route["capability"] == "image_to_video"
    assert prod_route["primary_provider"] == "shopaikey_video"
    assert prod_route["primary_model"] == "veo3.1-fast"
    assert prod_route["secondary_provider"] == "key4u_video"
    assert prod_route["secondary_model"] == "veo3.1-components"
    assert prod_route["provider"] == "shopaikey_video"
    assert prod_route["model"] == "veo3.1-fast"
    assert prod_route["max_single_task_seconds"] == 10
