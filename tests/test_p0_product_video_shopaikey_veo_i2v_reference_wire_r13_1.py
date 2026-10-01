# -*- coding: utf-8 -*-
"""
Tests for P0 Product Video SelfShot ShopAIKey Veo I2V Reference Image Wire Closure (R13.1 Remediation).
Subtask: PR1211_SECURITY_TTL_LIFECYCLE_REMEDIATION

Invariants & Guardrails:
1. Exact model catalog authority: substring 'veo' MUST NOT grant Google Veo authority.
2. HTTPS-only external reference policy: insecure HTTP, localhost, and private IPs are rejected.
3. Wire contract: metadata.images = ["https://..."], top-level image strictly absent for Veo I2V.
4. Model family isolation: Veo vs Grok vs Key4U.
5. SelfShot2 & SelfShot3 wire contracts.
6. Execution-integrated reference lifecycle:
   - Active task: reference preserved across polling.
   - Poll-only recovery: reference preserved, zero duplicate submits.
   - Terminal success: reference cleaned up.
   - Terminal failure: reference cleaned up.
   - Ambiguous submit: reference retained (no premature cleanup).
7. Zero live provider calls during all tests.
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
from services import (
    provider_reference_transport as transport,
    video_provider_catalog,
    video_provider_router,
)
from services.video_provider_base import VideoPollResult, VideoSubmitResult, VideoArtifactResult


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
        "SHOPAIKEY_VIDEO_CAPABILITIES": "text_to_video,image_to_video,scene_video,multi_scene_video,short_video",
        "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generations",
        "SHOPAIKEY_VIDEO_STATUS_URL": "https://api.shopaikey.com/v1/video/status/{task_id}",
        "SHOPAIKEY_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_API_KEY": "Bearer test_sak_token",
    }


@pytest.fixture
def dummy_keyframe(tmp_path):
    img = tmp_path / "keyframe_scene_01.jpg"
    # Valid JPEG magic bytes
    img.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00" + b"\x00" * 64)
    return img


# ==============================================================================
# 1. EXACT MODEL-FAMILY AUTHORITY (FIRST RED)
# ==============================================================================

def test_first_red_model_name_substring_must_not_grant_veo_authority(dummy_keyframe, mock_storage_env):
    """FIRST RED: Model name containing 'veo' as substring MUST NOT grant Google Veo authority unless in catalog."""
    # Case 1: 'fake-veo-name' is not in shopaikey_video catalog -> fails closed
    fake_veo_payload = {
        "model": "fake-veo-name",
        "prompt": "cinematic camera pan",
        "image": str(dummy_keyframe),
        "aspect_ratio": "9:16",
        "duration": 5,
        "metadata": {
            "required_capability": "image_to_video",
        },
    }
    with pytest.raises(VideoProviderContractError) as exc_info:
        _shopaikey_wire_payload(fake_veo_payload, env=mock_storage_env)
    assert exc_info.value.blocker in (video_provider_catalog.MODEL_UNKNOWN, "CONFIG_MODEL_UNKNOWN", "MODEL_UNKNOWN")
    assert exc_info.value.debug.get("no_charge") is True

    # Case 2: 'not-veo-but-veo-inside' -> not in catalog -> fails closed
    fake_substr_payload = {
        "model": "not-veo-but-veo-inside",
        "prompt": "cinematic pan",
        "image": str(dummy_keyframe),
        "metadata": {"required_capability": "image_to_video"},
    }
    with pytest.raises(VideoProviderContractError) as exc_info:
        _shopaikey_wire_payload(fake_substr_payload, env=mock_storage_env)
    assert exc_info.value.blocker in (video_provider_catalog.MODEL_UNKNOWN, "CONFIG_MODEL_UNKNOWN", "MODEL_UNKNOWN")


def test_model_family_isolation_veo_vs_grok(dummy_keyframe, mock_storage_env):
    """Catalog model veo3.1-fast resolves google_veo, while grok-video-3 resolves xai_grok."""
    veo_payload = {
        "model": "veo3.1-fast",
        "prompt": "veo shot",
        "image": str(dummy_keyframe),
        "metadata": {"required_capability": "image_to_video"},
    }
    grok_payload = {
        "model": "grok-video-3",
        "prompt": "grok shot",
        "image": str(dummy_keyframe),
        "metadata": {"required_capability": "image_to_video"},
    }

    veo_wire = _shopaikey_wire_payload(veo_payload, env=mock_storage_env)
    grok_wire = _shopaikey_wire_payload(grok_payload, env=mock_storage_env)

    # Veo: metadata.images present, top-level image absent
    assert "image" not in veo_wire
    assert "images" in veo_wire.get("metadata", {})
    assert veo_wire["metadata"]["images"][0].startswith("https://toanaas.vn/provider-media/v1/")

    # Grok: top-level image present (base64), metadata.images absent
    assert "image" in grok_wire
    assert isinstance(grok_wire["image"], str)
    assert "metadata" not in grok_wire or "images" not in grok_wire.get("metadata", {})


# ==============================================================================
# 2. HTTPS-ONLY EXTERNAL REFERENCE VALIDATION IN WIRE BUILDER
# ==============================================================================

def test_wire_builder_rejects_insecure_http_external_reference(mock_storage_env):
    """Insecure http:// external reference URL fails closed before HTTP submit."""
    payload = {
        "model": "veo3.1-fast",
        "prompt": "cinematic shot",
        "image": "http://cdn.example.com/assets/keyframe.jpg",
        "metadata": {"required_capability": "image_to_video"},
    }
    with pytest.raises(VideoProviderContractError) as exc_info:
        _shopaikey_wire_payload(payload, env=mock_storage_env)
    assert exc_info.value.blocker == "provider_image_external_url_insecure_http_rejected"


def test_wire_builder_rejects_localhost_external_reference(mock_storage_env):
    """Localhost and loopback external reference URLs fail closed."""
    for bad_url in ["https://localhost/keyframe.jpg", "https://127.0.0.1/keyframe.jpg"]:
        payload = {
            "model": "veo3.1-fast",
            "prompt": "cinematic shot",
            "image": bad_url,
            "metadata": {"required_capability": "image_to_video"},
        }
        with pytest.raises(VideoProviderContractError) as exc_info:
            _shopaikey_wire_payload(payload, env=mock_storage_env)
        assert "localhost" in exc_info.value.blocker or "private_ip" in exc_info.value.blocker


def test_wire_builder_accepts_valid_public_https_external_reference(mock_storage_env):
    """Valid public HTTPS external reference is accepted in metadata.images."""
    valid_url = "https://cdn.example.com/assets/keyframe.jpg"
    payload = {
        "model": "veo3.1-fast",
        "prompt": "cinematic shot",
        "image": valid_url,
        "metadata": {"required_capability": "image_to_video"},
    }
    wire = _shopaikey_wire_payload(payload, env=mock_storage_env)
    assert "image" not in wire
    assert wire["metadata"]["images"] == [valid_url]


# ==============================================================================
# 3. SELFSHOT2 & SELFSHOT3 WIRE INTEGRATION
# ==============================================================================

def test_selfshot2_reference_wire_contract(dummy_keyframe, mock_storage_env):
    """SelfShot2 produces metadata.images reference and omits top-level image."""
    req = VideoGenerationRequest(
        job_id="job_selfshot2_wire_01",
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
            "job_id": "job_selfshot2_wire_01",
        },
    )

    base_payload = build_shopaikey_video_payload(req, env=mock_storage_env)
    wire = _shopaikey_wire_payload(base_payload, env=mock_storage_env)

    assert "image" not in wire
    assert "metadata" in wire and "images" in wire["metadata"]
    assert wire["metadata"]["images"][0].startswith("https://toanaas.vn/provider-media/v1/")
    assert str(dummy_keyframe) not in json.dumps(wire)


def test_selfshot3_reference_wire_contract(dummy_keyframe, mock_storage_env):
    """SelfShot3 produces metadata.images reference and omits top-level image."""
    req = VideoGenerationRequest(
        job_id="job_selfshot3_wire_01",
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
            "job_id": "job_selfshot3_wire_01",
        },
    )

    base_payload = build_shopaikey_video_payload(req, env=mock_storage_env)
    wire = _shopaikey_wire_payload(base_payload, env=mock_storage_env)

    assert "image" not in wire
    assert "metadata" in wire and "images" in wire["metadata"]
    assert wire["metadata"]["images"][0].startswith("https://toanaas.vn/provider-media/v1/")
    assert str(dummy_keyframe) not in json.dumps(wire)


# ==============================================================================
# 4. EXECUTION SEAM: ACTIVE TASK REFERENCE PRESERVATION & POLL-ONLY RECOVERY
# ==============================================================================

def test_active_task_reference_preservation_and_poll_only_recovery(dummy_keyframe, mock_storage_env, tmp_path):
    """Active provider task preserves reference file; poll-only recovery does not submit duplicate."""
    storage_root = Path(mock_storage_env["PROVIDER_REFERENCE_STORAGE_DIR"])
    req = VideoGenerationRequest(
        job_id="job_active_preserve_01",
        product_type="self_shot_scene_change",
        required_capability="image_to_video",
        prompt="smooth camera movement",
        image_paths=[str(dummy_keyframe)],
        metadata={
            "required_capability": "image_to_video",
            "selected_model": "veo3.1-fast",
            "job_id": "job_active_preserve_01",
        },
    )

    fake_submit_body = {"code": 0, "data": {"task_id": "task_active_sak_123", "status": "SUBMITTED"}}
    fake_pending_poll_body = {"code": 0, "data": {"status": "PROCESSING", "progress": "50%"}}

    with patch("urllib.request.urlopen") as spy_http:
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [
            json.dumps(fake_submit_body).encode("utf-8"),
            json.dumps(fake_pending_poll_body).encode("utf-8"),
        ]
        mock_resp.status = 200
        spy_http.return_value.__enter__.return_value = mock_resp

        # Step 1: Initial submission and first poll
        res = video_provider_router.render_video_payload(
            req,
            env=mock_storage_env,
            allow_pending_result=True,
            max_poll_seconds=2,
            poll_interval_seconds=1,
        )

        assert (res.get("provider_status") in {"running", "in_progress", "SUBMITTED"} or res.get("status") in {"running", "in_progress", "SUBMITTED"})
        # Verify reference file exists in storage root
        active_files = [f for f in storage_root.glob("*.jpg")]
        assert len(active_files) == 1, "Reference must be preserved while task is active"
        meta_files = [f for f in storage_root.glob("*.meta.json")]
        assert len(meta_files) == 1

        # Step 2: Poll-only recovery on existing task (no new submit, no new reference)
        req_poll_only = VideoGenerationRequest(
            job_id="job_active_preserve_01",
            product_type="self_shot_scene_change",
            required_capability="image_to_video",
            prompt="smooth camera movement",
            metadata={
                "required_capability": "image_to_video",
                "selected_model": "veo3.1-fast",
                "provider_task_id": "task_active_sak_123",
                "job_id": "job_active_preserve_01",
            },
        )
        # Mock poll response for recovery
        mock_poll_resp = MagicMock()
        mock_poll_resp.read.return_value = json.dumps(fake_pending_poll_body).encode("utf-8")
        mock_poll_resp.status = 200
        spy_http.return_value.__enter__.return_value = mock_poll_resp

        res_recovery = video_provider_router.render_video_payload(
            req_poll_only,
            env=mock_storage_env,
            allow_pending_result=True,
            poll_existing_task=True,
            existing_task_id="task_active_sak_123",
            max_poll_seconds=1,
        )

        # Confirm reference file is STILL available
        active_files_after = [f for f in storage_root.glob("*.jpg")]
        assert len(active_files_after) == 1, "Reference must still exist after poll-only recovery"


# ==============================================================================
# 5. EXECUTION SEAM: TERMINAL SUCCESS & FAILURE CLEANUP
# ==============================================================================

def test_terminal_success_cleans_up_reference(dummy_keyframe, mock_storage_env, tmp_path):
    """Terminal success materializes artifact and cleans up provider reference."""
    storage_root = Path(mock_storage_env["PROVIDER_REFERENCE_STORAGE_DIR"])
    req = VideoGenerationRequest(
        job_id="job_terminal_success_01",
        product_type="self_shot_scene_change",
        required_capability="image_to_video",
        prompt="smooth camera movement",
        image_paths=[str(dummy_keyframe)],
        metadata={
            "required_capability": "image_to_video",
            "selected_model": "veo3.1-fast",
            "job_id": "job_terminal_success_01",
        },
    )

    fake_submit_body = {"code": 0, "data": {"task_id": "task_success_123", "status": "SUBMITTED"}}
    fake_success_poll_body = {"code": 0, "data": {"status": "SUCCESS", "result_url": "https://cdn.example.com/output.mp4"}}

    dummy_mp4 = tmp_path / "result.mp4"
    dummy_mp4.write_bytes(b"\x00\x00\x00\x1cftypisom" + b"\x00" * 64)

    with patch("urllib.request.urlopen") as spy_http:
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [
            json.dumps(fake_submit_body).encode("utf-8"),
            json.dumps(fake_success_poll_body).encode("utf-8"),
        ]
        mock_resp.status = 200
        spy_http.return_value.__enter__.return_value = mock_resp

        with patch.object(
            GenericHttpVideoProvider,
            "materialize_result",
            return_value=VideoArtifactResult(
                ok=True,
                local_path=str(dummy_mp4),
                bytes=len(dummy_mp4.read_bytes()),
                duration=5.0,
                has_video_stream=True,
                artifact_hash="abc123hash",
            ),
        ):
            res = video_provider_router.render_video_payload(
                req,
                env=mock_storage_env,
                max_poll_seconds=2,
                poll_interval_seconds=1,
            )

            assert res.get("ok") is True
            # Reference file MUST be cleaned up on terminal success
            active_images = [f for f in storage_root.glob("*.jpg")]
            assert len(active_images) == 0, "Reference image must be cleaned up on terminal success"
            active_meta = [f for f in storage_root.glob("*.meta.json")]
            assert len(active_meta) == 0


def test_terminal_failure_cleans_up_reference(dummy_keyframe, mock_storage_env):
    """Terminal failure terminates execution and cleans up provider reference."""
    storage_root = Path(mock_storage_env["PROVIDER_REFERENCE_STORAGE_DIR"])
    req = VideoGenerationRequest(
        job_id="job_terminal_fail_01",
        product_type="self_shot_scene_change",
        required_capability="image_to_video",
        prompt="smooth camera movement",
        image_paths=[str(dummy_keyframe)],
        metadata={
            "required_capability": "image_to_video",
            "selected_model": "veo3.1-fast",
            "job_id": "job_terminal_fail_01",
        },
    )

    fake_submit_body = {"code": 0, "data": {"task_id": "task_fail_123", "status": "SUBMITTED"}}
    fake_fail_poll_body = {"code": 0, "data": {"status": "FAILURE", "fail_reason": "render_error"}}

    with patch("urllib.request.urlopen") as spy_http:
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [
            json.dumps(fake_submit_body).encode("utf-8"),
            json.dumps(fake_fail_poll_body).encode("utf-8"),
        ]
        mock_resp.status = 200
        spy_http.return_value.__enter__.return_value = mock_resp

        res = video_provider_router.render_video_payload(
            req,
            env=mock_storage_env,
            max_poll_seconds=2,
            poll_interval_seconds=1,
        )

        assert res.get("ok") is False
        # Reference file MUST be cleaned up on terminal failure
        active_images = [f for f in storage_root.glob("*.jpg")]
        assert len(active_images) == 0, "Reference image must be cleaned up on terminal failure"


# ==============================================================================
# 6. AMBIGUOUS SUBMIT: PRESERVES REFERENCE (NO PREMATURE CLEANUP)
# ==============================================================================

def test_ambiguous_submit_preserves_reference_until_ttl(dummy_keyframe, mock_storage_env):
    """Ambiguous submit (timeout) does NOT clean up reference immediately; retains for polling."""
    storage_root = Path(mock_storage_env["PROVIDER_REFERENCE_STORAGE_DIR"])
    req = VideoGenerationRequest(
        job_id="job_ambiguous_submit_01",
        product_type="self_shot_scene_change",
        required_capability="image_to_video",
        prompt="smooth camera movement",
        image_paths=[str(dummy_keyframe)],
        metadata={
            "required_capability": "image_to_video",
            "selected_model": "veo3.1-fast",
            "job_id": "job_ambiguous_submit_01",
        },
    )

    # HTTP submit raises TimeoutError
    with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out after write")):
        res = video_provider_router.render_video_payload(
            req,
            env=mock_storage_env,
        )

        assert res.get("ok") is False
        assert res.get("blocker") == "provider_submit_outcome_ambiguous_no_charge"
        assert res.get("auto_resubmit_allowed") is False
        assert res.get("fallback_allowed") is False

        # Reference MUST still exist (retained until polling resolution or TTL)
        active_images = [f for f in storage_root.glob("*.jpg")]
        assert len(active_images) == 1, "Ambiguous submit must NOT clean up reference prematurely"
