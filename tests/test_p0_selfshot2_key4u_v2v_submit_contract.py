"""Tests for P0 Self-Shot V2V Submit Contract Correction (Fail-Closed Gates & Hidden Fallback Guard).

Mandatory Verification:
CASE_A: Key4U + /text2video + required V2V -> FAIL_CLOSED (provider_capability_contract_mismatch), provider calls = 0, fallback calls = 0.
CASE_B: Catalog says video_to_video but no proven wire adapter -> FAIL_CLOSED, calls = 0.
CASE_C: Generic multipart + no provider-specific V2V proof -> FAIL_CLOSED, calls = 0.
CASE_D: Unknown endpoint naming -> FAIL_CLOSED, calls = 0.
CASE_E: Primary capability mismatch + fallback provider configured -> no fallback called, total provider calls = 0.
CASE_F: Tier 500 duration = 5s preserved.
CASE_G: Source segment missing/unbound -> FAIL_CLOSED.
CASE_H: Text-only fallback -> FORBIDDEN.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from services import video_ai_edit_provider
from services import video_ai_real_pricing
from services import video_real_render_connector
from services.video_real_render_connector import RealVideoRenderError


# ---------------------------------------------------------------------------
# CASE_A: Key4U + /text2video + required V2V -> FAIL_CLOSED
# ---------------------------------------------------------------------------

def test_case_a_key4u_text2video_fails_closed_before_http(tmp_path: Path):
    """Key4U with /text2video endpoint must fail pre-submit validation with provider_capability_contract_mismatch and 0 HTTP calls."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_12345")

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.click/kling/v1/videos/text2video",
        poll_url="https://api.key4u.click/kling/v1/videos/text2video/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer real_secret_token",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    # 1. Endpoint classification
    cap = video_ai_edit_provider.classify_endpoint_capability(cfg.submit_url)
    assert cap == "text_to_video"

    # 2. Pre-submit validation
    val = video_ai_edit_provider.validate_provider_config(cfg, required_capability="video_to_video")
    assert val["ok"] is False
    assert val["reason"] == "provider_capability_contract_mismatch"
    assert "provider_capability_contract_mismatch" in val["invalid_fields"]
    assert val["endpoint_capability"] == "text_to_video"

    # 3. submit_video_edit must raise before any HTTP request
    mock_opener = MagicMock()
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path=str(sample_video),
            prompt="cinematic edit",
            negative_prompt="",
            aspect_ratio="9:16",
            duration_seconds=5,
            job_id="test-job-45",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=mock_opener,
        )

    assert exc_info.value.reason == "provider_capability_contract_mismatch"
    assert mock_opener.call_count == 0  # PROVIDER_CALLS = 0


# ---------------------------------------------------------------------------
# CASE_B: Catalog says video_to_video but no proven wire adapter -> FAIL_CLOSED
# ---------------------------------------------------------------------------

def test_case_b_catalog_v2v_without_proven_wire_adapter_fails_closed(tmp_path: Path):
    """Catalog metadata claiming video_to_video is not proof of wire contract; must fail closed."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_12345")

    # kling-3.0-turbo has video_to_video in catalog
    contract = video_ai_edit_provider.model_contract("key4u_video", "kling-3.0-turbo")
    assert contract["known"] is True
    assert contract["video_to_video"] is True

    # But Key4U has no proven V2V wire adapter
    assert video_ai_edit_provider.KEY4U_V2V_WIRE_CONTRACT == "UNAVAILABLE_FAIL_CLOSED"
    assert not video_ai_edit_provider.has_proven_v2v_wire_contract("key4u_video", "kling-3.0-turbo")

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.click/kling/v1/videos/text2video",
        poll_url="https://api.key4u.click/kling/v1/videos/text2video/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer real_secret_token",
        model="kling-3.0-turbo",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    val = video_ai_edit_provider.validate_provider_config(cfg, required_capability="video_to_video")
    assert val["ok"] is False
    assert val["reason"] == "provider_capability_contract_mismatch"

    mock_opener = MagicMock()
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path=str(sample_video),
            prompt="cinematic edit",
            negative_prompt="",
            aspect_ratio="9:16",
            duration_seconds=5,
            job_id="test-job-45-b",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=mock_opener,
        )

    assert exc_info.value.reason == "provider_capability_contract_mismatch"
    assert mock_opener.call_count == 0


# ---------------------------------------------------------------------------
# CASE_C: Generic multipart without provider-specific V2V proof -> FAIL_CLOSED
# ---------------------------------------------------------------------------

def test_case_c_generic_multipart_without_proven_wire_adapter_fails_closed(tmp_path: Path):
    """Generic multipart interface without a proven provider-specific V2V wire adapter fails closed."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_12345")

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="generic_http",
        enabled=True,
        submit_url="https://api.generic.ai/v1/video/edit",
        poll_url="https://api.generic.ai/v1/video/edit/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer generic_secret_token",
        model="generic-v2v-model",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    assert not video_ai_edit_provider.has_proven_v2v_wire_contract("generic_http", "generic-v2v-model")

    val = video_ai_edit_provider.validate_provider_config(cfg, required_capability="video_to_video")
    assert val["ok"] is False
    assert val["reason"] == "provider_capability_contract_mismatch"

    mock_opener = MagicMock()
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path=str(sample_video),
            prompt="edit",
            negative_prompt="",
            aspect_ratio="9:16",
            duration_seconds=5,
            job_id="test-job-c",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=mock_opener,
        )

    assert exc_info.value.reason == "provider_capability_contract_mismatch"
    assert mock_opener.call_count == 0


# ---------------------------------------------------------------------------
# CASE_D: Unknown endpoint naming -> FAIL_CLOSED
# ---------------------------------------------------------------------------

def test_case_d_unknown_endpoint_naming_fails_closed(tmp_path: Path):
    """Endpoints with unknown or custom naming classify as unknown and fail closed for V2V."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_12345")

    urls = [
        "https://api.key4u.click/custom/unverified/endpoint",
        "https://api.example.com/v1/unknown_service",
        "https://api.key4u.click/v1/arbitrary_path",
    ]

    for submit_url in urls:
        cap = video_ai_edit_provider.classify_endpoint_capability(submit_url)
        assert cap == "unknown"

        cfg = video_ai_edit_provider.AiEditProviderConfig(
            provider_name="key4u_video",
            enabled=True,
            submit_url=submit_url,
            poll_url=f"{submit_url}/{{task_id}}",
            auth_header_name="Authorization",
            auth_header_value="Bearer real_token",
            model="kling-video",
            interface="video_to_video_multipart",
            capabilities=("video_to_video",),
        )

        val = video_ai_edit_provider.validate_provider_config(cfg, required_capability="video_to_video")
        assert val["ok"] is False
        assert val["reason"] == "provider_capability_contract_mismatch"

        mock_opener = MagicMock()
        with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc:
            video_ai_edit_provider.submit_video_edit(
                cfg,
                source_video_path=str(sample_video),
                prompt="edit",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="test-d",
                submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
                opener=mock_opener,
            )
        assert exc.value.reason == "provider_capability_contract_mismatch"
        assert mock_opener.call_count == 0


# ---------------------------------------------------------------------------
# CASE_E: Primary capability mismatch + fallback provider -> NO FALLBACK CALLED
# ---------------------------------------------------------------------------

def test_case_e_primary_capability_mismatch_blocks_hidden_fallback(tmp_path: Path):
    """When primary provider has capability mismatch, hidden fallback is strictly blocked and 0 provider calls are made."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"SOURCE_MP4_VALID_BYTES")

    # Controlled fallback decision unit guard check
    decision = video_ai_edit_provider.controlled_fallback_decision(
        public_confirm_provenance=True,
        primary_status="failed",
        primary_task_alive=False,
        fallback_count=0,
        candidate=video_ai_edit_provider.AiEditProviderConfig(
            provider_name="shopaikey_video",
            enabled=True,
            submit_url="https://api.shopaikey.com/v1/video",
            poll_url="https://api.shopaikey.com/v1/video/{task_id}",
            auth_header_name="Authorization",
            auth_header_value="Bearer fallback_token",
            model="veo3.1-fast",
            interface="video_to_video_multipart",
            capabilities=("video_to_video",),
        ),
        primary_error="provider_capability_contract_mismatch",
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "capability_contract_mismatch_fallback_forbidden"

    # End-to-end connector render guard check:
    # Key4U has text2video URL (capability mismatch).
    # ShopAiKey is in provider_order as fallback candidate.
    submit_spy = MagicMock(wraps=video_ai_edit_provider.submit_video_edit)
    mock_urlopen = MagicMock()

    with patch.dict(os.environ, {
        "KEY4U_VIDEO_TO_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_TO_VIDEO_SUBMIT_URL": "https://api.key4u.click/kling/v1/videos/text2video",
        "KEY4U_VIDEO_TO_VIDEO_POLL_URL": "https://api.key4u.click/kling/v1/videos/text2video/{task_id}",
        "KEY4U_VIDEO_TO_VIDEO_AUTH_HEADER_VALUE": "Bearer key4u_token",
        "KEY4U_VIDEO_TO_VIDEO_MODEL": "kling-video",
        "SHOPAIKEY_VIDEO_TO_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_TO_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video",
        "SHOPAIKEY_VIDEO_TO_VIDEO_POLL_URL": "https://api.shopaikey.com/v1/video/{task_id}",
        "SHOPAIKEY_VIDEO_TO_VIDEO_AUTH_HEADER_VALUE": "Bearer shopaikey_token",
        "SHOPAIKEY_VIDEO_TO_VIDEO_MODEL": "veo3.1-fast",
    }), patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(source_file)), \
        patch("services.video_ai_edit_provider.submit_video_edit", submit_spy), \
        patch("urllib.request.urlopen", mock_urlopen):

        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_selfshot2_video_to_video(
                job={
                    "source_video_local_path": str(source_file),
                    "quality_tier": 500,
                    "public_user_confirmed": True,
                    "submit_source": "public_user_final_confirm",
                },
                asset_pack={},
                raw_path=str(tmp_path / "raw.mp4"),
                provider_order=["key4u_video", "shopaikey_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                scene_index=0,
            )

        # 1. Primary provider fails closed immediately on capability mismatch
        assert exc_info.value.diagnostics["blocker"] == "provider_capability_contract_mismatch"
        assert exc_info.value.diagnostics["no_charge"] is True
        assert exc_info.value.diagnostics["provider_attempted"] is False
        assert exc_info.value.diagnostics.get("fallback_blocked_reason") == "capability_contract_mismatch_fallback_forbidden"

        # 2. Key4U validation failed pre-submit, so 0 HTTP requests were sent
        assert mock_urlopen.call_count == 0

        # 3. Fallback provider (ShopAiKey) was NEVER submitted (0 fallback calls)
        assert not any(call.args and getattr(call.args[0], "provider_name", "") == "shopaikey_video" for call in submit_spy.call_args_list)


# ---------------------------------------------------------------------------
# CASE_F: Tier 500 duration = 5s preserved
# ---------------------------------------------------------------------------

def test_case_f_tier_500_duration_preserved():
    """Tier 500 duration contract is exactly 5 seconds."""
    route = video_ai_real_pricing.product_video_route_by_tier(500)
    assert route["seconds_per_scene"] == 5
    assert route["tier_id"] == 500


# ---------------------------------------------------------------------------
# CASE_G: Source segment missing / unbound -> FAIL_CLOSED
# ---------------------------------------------------------------------------

def test_case_g_unbound_missing_source_fails_closed(tmp_path: Path):
    """Missing or non-materialized source video fails closed immediately with no_charge."""
    nonexistent = tmp_path / "does_not_exist.mp4"

    with pytest.raises(RealVideoRenderError) as exc_info:
        video_real_render_connector._render_selfshot2_video_to_video(
            job={
                "source_video_local_path": str(nonexistent),
                "quality_tier": 500,
                "public_user_confirmed": True,
                "submit_source": "public_user_final_confirm",
            },
            asset_pack={},
            raw_path=str(tmp_path / "out.mp4"),
            provider_order=["key4u"],
            fallback_prompt="prompt",
            aspect_ratio="9:16",
            scene_index=0,
        )

    diag = exc_info.value.diagnostics
    assert diag["ok"] is False
    assert diag["no_charge"] is True
    assert diag["provider_attempted"] is False
    assert diag["blocker"] == "selfshot2_source_video_not_materialized"


# ---------------------------------------------------------------------------
# CASE_H: Text-only fallback -> FORBIDDEN
# ---------------------------------------------------------------------------

def test_case_h_text_only_fallback_forbidden(tmp_path: Path):
    """Text-only fallback is strictly forbidden in SELFSHOT2."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"VIDEO_CONTENT")

    # If V2V provider fails, connector fails closed with RealVideoRenderError
    # and NEVER falls back to text-only generation.
    mock_cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.click/kling/v1/videos/text2video",
        poll_url="https://api.key4u.click/kling/v1/videos/text2video/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer key4u_token",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    with patch("services.video_real_render_connector._selfshot3_provider_configs", return_value=[mock_cfg]), \
         patch("services.video_real_render_connector._materialize_selfshot2_source_segment", return_value=str(source_file)):

        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_selfshot2_video_to_video(
                job={
                    "source_video_local_path": str(source_file),
                    "quality_tier": 500,
                    "public_user_confirmed": True,
                    "submit_source": "public_user_final_confirm",
                },
                asset_pack={},
                raw_path=str(tmp_path / "out.mp4"),
                provider_order=["key4u"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
                scene_index=0,
            )

        diag = exc_info.value.diagnostics
        assert diag["ok"] is False
        assert diag["no_charge"] is True
        assert diag["provider_attempted"] is False
