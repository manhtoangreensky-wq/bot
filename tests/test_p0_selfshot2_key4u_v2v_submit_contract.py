"""Tests for P0 Self-Shot V2V Submit Contract Correction (Fail-Closed Gates & Authority Model).

Mandatory Regression Verification:
1. internal/test harness URL cannot become production V2V authority
2. same URL cannot prove V2V for Key4U
3. same URL cannot prove V2V for generic provider
4. Key4U text2video remains blocked
5. Key4U image2video remains blocked for V2V
6. unknown endpoint remains blocked
7. model catalog video_to_video capability alone is insufficient
8. no fallback after primary capability mismatch
9. SelfShot2 mismatch fails before provider HTTP
10. SelfShot3 mismatch fails before provider HTTP
11. Provider-success positive-path tests may inject test-only seam/mock without production authority
12. Tier 500 duration = 5s preserved
13. Source segment missing/unbound -> FAIL_CLOSED
14. Text-only fallback -> FORBIDDEN
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
# 1. Internal/test harness URL cannot become production V2V authority
# ---------------------------------------------------------------------------

def test_1_internal_test_harness_url_cannot_become_production_v2v_authority():
    """Production PROVEN_V2V_WIRE_ADAPTERS must contain 0 test-only endpoints; test URL cannot prove V2V."""
    test_harness_url = "https://api.key4u.vn/v1/video/generations"

    # Production authority set has 0 test-only endpoints
    assert test_harness_url not in video_ai_edit_provider.PROVEN_V2V_WIRE_ADAPTERS
    assert len(video_ai_edit_provider.PROVEN_V2V_WIRE_ADAPTERS) == 0

    # has_proven_v2v_wire_contract must NOT return True merely because of this URL
    assert not video_ai_edit_provider.has_proven_v2v_wire_contract(
        "key4u_video", "kling-video", test_harness_url
    )


# ---------------------------------------------------------------------------
# 2. Same test harness URL cannot prove V2V for Key4U
# ---------------------------------------------------------------------------

def test_2_same_url_cannot_prove_v2v_for_key4u(tmp_path: Path):
    """Key4U using test harness URL cannot become V2V-proven; pre-submit validation fails closed."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_KEY4U")

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.vn/v1/video/generations",
        poll_url="https://api.key4u.vn/v1/video/generations/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer real_token",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    # 1. has_proven_v2v_wire_contract must return False
    assert not video_ai_edit_provider.has_proven_v2v_wire_contract(
        cfg.provider_name, cfg.model, cfg.submit_url
    )

    # 2. validate_provider_config fails closed with mismatch
    val = video_ai_edit_provider.validate_provider_config(cfg, required_capability="video_to_video")
    assert val["ok"] is False
    assert val["reason"] == "provider_capability_contract_mismatch"
    assert "provider_capability_contract_mismatch" in val["invalid_fields"]

    # 3. Production submit_video_edit (without opener) raises before HTTP
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path=str(sample_video),
            prompt="edit",
            negative_prompt="",
            aspect_ratio="9:16",
            duration_seconds=5,
            job_id="test-job-key4u-url",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
        )
    assert exc_info.value.reason == "provider_capability_contract_mismatch"


# ---------------------------------------------------------------------------
# 3. Same test harness URL cannot prove V2V for generic provider
# ---------------------------------------------------------------------------

def test_3_same_url_cannot_prove_v2v_for_generic_provider(tmp_path: Path):
    """A non-Key4U generic provider using the same test harness URL cannot become V2V-proven."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_GENERIC")

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="generic_http",
        enabled=True,
        submit_url="https://api.key4u.vn/v1/video/generations",
        poll_url="https://api.key4u.vn/v1/video/generations/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer generic_token",
        model="generic-model",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    # 1. has_proven_v2v_wire_contract must return False
    assert not video_ai_edit_provider.has_proven_v2v_wire_contract(
        cfg.provider_name, cfg.model, cfg.submit_url
    )

    # 2. validate_provider_config fails closed
    val = video_ai_edit_provider.validate_provider_config(cfg, required_capability="video_to_video")
    assert val["ok"] is False
    assert val["reason"] == "provider_capability_contract_mismatch"

    # 3. submit_video_edit fails closed before HTTP
    mock_opener = MagicMock()
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path=str(sample_video),
            prompt="edit",
            negative_prompt="",
            aspect_ratio="9:16",
            duration_seconds=5,
            job_id="test-job-generic-url",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=mock_opener,
        )
    assert exc_info.value.reason == "provider_capability_contract_mismatch"
    assert mock_opener.call_count == 0


# ---------------------------------------------------------------------------
# 4. Key4U text2video remains blocked
# ---------------------------------------------------------------------------

def test_4_key4u_text2video_remains_blocked(tmp_path: Path):
    """Key4U with /text2video endpoint must classify as text_to_video and fail closed before HTTP."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_T2V")

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

    # Classification
    assert video_ai_edit_provider.classify_endpoint_capability(cfg.submit_url) == "text_to_video"

    # Pre-submit validation
    val = video_ai_edit_provider.validate_provider_config(cfg, required_capability="video_to_video")
    assert val["ok"] is False
    assert val["reason"] == "provider_capability_contract_mismatch"

    # submit_video_edit raises before HTTP even if opener spy passed
    mock_opener = MagicMock()
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path=str(sample_video),
            prompt="cinematic edit",
            negative_prompt="",
            aspect_ratio="9:16",
            duration_seconds=5,
            job_id="test-job-4",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=mock_opener,
        )
    assert exc_info.value.reason == "provider_capability_contract_mismatch"
    assert mock_opener.call_count == 0


# ---------------------------------------------------------------------------
# 5. Key4U image2video remains blocked for V2V
# ---------------------------------------------------------------------------

def test_5_key4u_image2video_remains_blocked_for_v2v(tmp_path: Path):
    """Key4U with /image2video endpoint must classify as image_to_video and fail closed for V2V."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_I2V")

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.click/kling/v1/videos/image2video",
        poll_url="https://api.key4u.click/kling/v1/videos/image2video/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer real_secret_token",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    # Classification
    assert video_ai_edit_provider.classify_endpoint_capability(cfg.submit_url) == "image_to_video"

    # Pre-submit validation
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
            job_id="test-job-5",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=mock_opener,
        )
    assert exc_info.value.reason == "provider_capability_contract_mismatch"
    assert mock_opener.call_count == 0


# ---------------------------------------------------------------------------
# 6. Unknown endpoint remains blocked
# ---------------------------------------------------------------------------

def test_6_unknown_endpoint_remains_blocked(tmp_path: Path):
    """Endpoints with unknown or custom naming classify as unknown and fail closed for V2V."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_UNKNOWN")

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
                job_id="test-6",
                submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
                opener=mock_opener,
            )
        assert exc.value.reason == "provider_capability_contract_mismatch"
        assert mock_opener.call_count == 0


# ---------------------------------------------------------------------------
# 7. Model catalog video_to_video capability alone is insufficient
# ---------------------------------------------------------------------------

def test_7_model_catalog_v2v_capability_alone_is_insufficient(tmp_path: Path):
    """Catalog metadata claiming video_to_video is not proof of wire contract; must fail closed."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_CATALOG")

    contract = video_ai_edit_provider.model_contract("key4u_video", "kling-3.0-turbo")
    assert contract["known"] is True
    assert contract["video_to_video"] is True

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
            job_id="test-job-7",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=mock_opener,
        )
    assert exc_info.value.reason == "provider_capability_contract_mismatch"
    assert mock_opener.call_count == 0


# ---------------------------------------------------------------------------
# 8. No fallback after primary capability mismatch
# ---------------------------------------------------------------------------

def test_8_no_fallback_after_primary_capability_mismatch():
    """controlled_fallback_decision must strictly reject candidate when primary has capability mismatch."""
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


# ---------------------------------------------------------------------------
# 9. SelfShot2 mismatch fails before provider HTTP
# ---------------------------------------------------------------------------

def test_9_selfshot2_mismatch_fails_before_provider_http(tmp_path: Path):
    """SelfShot2 connector fails closed on primary capability mismatch with 0 HTTP calls and 0 fallback calls."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"SOURCE_MP4_VALID_BYTES_SS2")

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

        diag = exc_info.value.diagnostics
        assert diag["blocker"] == "provider_capability_contract_mismatch"
        assert diag["no_charge"] is True
        assert diag["provider_attempted"] is False
        assert diag.get("fallback_blocked_reason") == "capability_contract_mismatch_fallback_forbidden"

        # 0 HTTP requests sent
        assert mock_urlopen.call_count == 0

        # Fallback provider was never submitted
        assert not any(call.args and getattr(call.args[0], "provider_name", "") == "shopaikey_video" for call in submit_spy.call_args_list)


# ---------------------------------------------------------------------------
# 10. SelfShot3 mismatch fails before provider HTTP
# ---------------------------------------------------------------------------

def test_10_selfshot3_mismatch_fails_before_provider_http(tmp_path: Path):
    """SelfShot3 connector fails closed on primary capability mismatch with 0 HTTP calls and 0 fallback calls."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"SOURCE_MP4_VALID_BYTES_SS3")

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
    }), patch("services.video_ai_edit_provider.submit_video_edit", submit_spy), \
        patch("urllib.request.urlopen", mock_urlopen):

        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_selfshot3_video_to_video(
                job={
                    "source_video_local_path": str(source_file),
                    "quality_tier": 500,
                    "public_user_confirmed": True,
                    "submit_source": "public_user_final_confirm",
                },
                asset_pack={},
                raw_path=str(tmp_path / "raw_ss3.mp4"),
                provider_order=["key4u_video", "shopaikey_video"],
                fallback_prompt="prompt",
                aspect_ratio="9:16",
            )

        diag = exc_info.value.diagnostics
        assert diag["blocker"] == "provider_capability_contract_mismatch"
        assert diag["no_charge"] is True
        assert diag["provider_attempted"] is False
        assert diag.get("fallback_blocked_reason") == "capability_contract_mismatch_fallback_forbidden"

        # 0 HTTP requests sent
        assert mock_urlopen.call_count == 0

        # Fallback provider was never submitted
        assert not any(call.args and getattr(call.args[0], "provider_name", "") == "shopaikey_video" for call in submit_spy.call_args_list)


# ---------------------------------------------------------------------------
# 11. Provider-success positive-path tests may inject test-only seam/mock
# ---------------------------------------------------------------------------

def test_11_positive_path_test_seam_mock_without_production_authority():
    """Positive-path unit tests may inject mock wire authority in test process without creating production authority."""
    test_url = "https://mock.test.local/v1/video/generations"

    # Prior to injection: not proven
    assert not video_ai_edit_provider.has_proven_v2v_wire_contract("test_provider", "test-model", test_url)

    # Injected test seam grants test authority during test execution
    video_ai_edit_provider.inject_test_v2v_wire_contract(test_url)
    try:
        assert video_ai_edit_provider.has_proven_v2v_wire_contract("test_provider", "test-model", test_url)
        # Production authority set remains strictly zero
        assert len(video_ai_edit_provider.PROVEN_V2V_WIRE_ADAPTERS) == 0
    finally:
        video_ai_edit_provider.clear_test_v2v_wire_contracts()

    # After cleanup: not proven
    assert not video_ai_edit_provider.has_proven_v2v_wire_contract("test_provider", "test-model", test_url)


# ---------------------------------------------------------------------------
# 12. Tier 500 duration contract is preserved
# ---------------------------------------------------------------------------

def test_12_tier_500_duration_preserved():
    """Tier 500 duration contract is exactly 5 seconds."""
    route = video_ai_real_pricing.product_video_route_by_tier(500)
    assert route["seconds_per_scene"] == 5
    assert route["tier_id"] == 500


# ---------------------------------------------------------------------------
# 13. Source segment missing / unbound -> FAIL_CLOSED
# ---------------------------------------------------------------------------

def test_13_unbound_missing_source_fails_closed(tmp_path: Path):
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
# 14. Text-only fallback -> FORBIDDEN
# ---------------------------------------------------------------------------

def test_14_text_only_fallback_forbidden(tmp_path: Path):
    """Text-only fallback is strictly forbidden in SELFSHOT2."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"VIDEO_CONTENT")

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
