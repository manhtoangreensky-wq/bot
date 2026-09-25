"""Tests for P0 Self-Shot V2V Submit Contract Correction (Fail-Closed Gates & Authority Model).

Required Minimum Contract Verifications:
1. no production mutable test V2V authority registry exists
2. no production inject_test_v2v_wire_contract function exists
3. invalid unknown endpoint + opener=None fails closed
4. invalid unknown endpoint + MagicMock opener fails closed
5. invalid unknown endpoint + plain callable opener fails closed
6. invalid unknown endpoint + custom opener object fails closed
7. transport call count remains 0 for all invalid configs
8. text2video V2V mismatch fails closed
9. image2video V2V mismatch fails closed
10. catalog capability alone remains insufficient
11. SelfShot2 mismatch makes zero HTTP calls
12. SelfShot3 mismatch makes zero HTTP calls
13. mismatch cannot trigger secondary provider fallback
14. Tier 500 duration remains 5 seconds
15. missing SelfShot source fails closed
16. text-only fallback remains forbidden
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
# 1. No production mutable test V2V authority registry exists
# ---------------------------------------------------------------------------

def test_1_no_production_mutable_test_v2v_authority_registry_exists():
    """Production module must NOT expose a mutable test proof registry."""
    assert not hasattr(video_ai_edit_provider, "_TEST_PROVEN_V2V_WIRE")


# ---------------------------------------------------------------------------
# 2. No production inject_test_v2v_wire_contract function exists
# ---------------------------------------------------------------------------

def test_2_no_production_inject_test_v2v_wire_contract_function_exists():
    """Production module must NOT expose test authority mutation APIs."""
    assert not hasattr(video_ai_edit_provider, "inject_test_v2v_wire_contract")
    assert not hasattr(video_ai_edit_provider, "clear_test_v2v_wire_contracts")


# ---------------------------------------------------------------------------
# 3. Invalid unknown endpoint + opener=None fails closed
# ---------------------------------------------------------------------------

def test_3_invalid_unknown_endpoint_opener_none_fails_closed(tmp_path: Path):
    """Unknown endpoint with opener=None fails closed before HTTP with provider_capability_contract_mismatch."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_UNKNOWN_NONE")

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.click/custom/unverified/endpoint",
        poll_url="https://api.key4u.click/custom/unverified/endpoint/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer real_token",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    val = video_ai_edit_provider.validate_provider_config(cfg, required_capability="video_to_video")
    assert val["ok"] is False
    assert val["reason"] == "provider_capability_contract_mismatch"

    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path=str(sample_video),
            prompt="edit",
            negative_prompt="",
            aspect_ratio="9:16",
            duration_seconds=5,
            job_id="test-3",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=None,
        )
    assert exc.value.reason == "provider_capability_contract_mismatch"


# ---------------------------------------------------------------------------
# 4. Invalid unknown endpoint + MagicMock opener fails closed
# ---------------------------------------------------------------------------

def test_4_invalid_unknown_endpoint_magicmock_opener_fails_closed(tmp_path: Path):
    """Unknown endpoint with MagicMock opener fails closed before HTTP; mock call count is 0."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_UNKNOWN_MOCK")

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.click/custom/unverified/endpoint",
        poll_url="https://api.key4u.click/custom/unverified/endpoint/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer real_token",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    mock_opener = MagicMock()
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path=str(sample_video),
            prompt="edit",
            negative_prompt="",
            aspect_ratio="9:16",
            duration_seconds=5,
            job_id="test-4",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=mock_opener,
        )
    assert exc.value.reason == "provider_capability_contract_mismatch"
    assert mock_opener.call_count == 0


# ---------------------------------------------------------------------------
# 5. Invalid unknown endpoint + plain callable opener fails closed
# ---------------------------------------------------------------------------

def test_5_invalid_unknown_endpoint_plain_callable_opener_fails_closed(tmp_path: Path):
    """Unknown endpoint with plain function/callable opener fails closed; transport is never reached."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_UNKNOWN_CALLABLE")

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.click/custom/unverified/endpoint",
        poll_url="https://api.key4u.click/custom/unverified/endpoint/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer real_token",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    calls = []

    def plain_callable_opener(*args, **kwargs):
        calls.append((args, kwargs))
        raise RuntimeError("plain_callable_opener must NEVER be called")

    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path=str(sample_video),
            prompt="edit",
            negative_prompt="",
            aspect_ratio="9:16",
            duration_seconds=5,
            job_id="test-5",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=plain_callable_opener,
        )
    assert exc.value.reason == "provider_capability_contract_mismatch"
    assert len(calls) == 0


# ---------------------------------------------------------------------------
# 6. Invalid unknown endpoint + custom opener object fails closed
# ---------------------------------------------------------------------------

def test_6_invalid_unknown_endpoint_custom_opener_object_fails_closed(tmp_path: Path):
    """Unknown endpoint with custom non-Mock opener instance fails closed; transport is never reached."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_UNKNOWN_CUSTOM")

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.click/custom/unverified/endpoint",
        poll_url="https://api.key4u.click/custom/unverified/endpoint/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer real_token",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    class CustomTransport:
        def __init__(self):
            self.calls = []

        def __call__(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            raise RuntimeError("CustomTransport.__call__ must NEVER be reached")

        def open(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            raise RuntimeError("CustomTransport.open must NEVER be reached")

    transport = CustomTransport()

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
            opener=transport,
        )
    assert exc.value.reason == "provider_capability_contract_mismatch"
    assert len(transport.calls) == 0


# ---------------------------------------------------------------------------
# 7. Transport call count remains 0 for all invalid configs
# ---------------------------------------------------------------------------

def test_7_transport_call_count_remains_zero_for_all_invalid_configs(tmp_path: Path):
    """Transport call count is strictly 0 across all invalid configurations and opener types."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"TEST_VIDEO_BYTES_ZERO_CALLS")

    invalid_urls = [
        "https://api.key4u.click/kling/v1/videos/text2video",
        "https://api.key4u.click/kling/v1/videos/image2video",
        "https://api.key4u.click/custom/unverified/endpoint",
        "https://api.example.com/v1/unknown_service",
    ]

    for submit_url in invalid_urls:
        cfg = video_ai_edit_provider.AiEditProviderConfig(
            provider_name="key4u_video",
            enabled=True,
            submit_url=submit_url,
            poll_url=f"{submit_url}/{{task_id}}",
            auth_header_name="Authorization",
            auth_header_value="Bearer token",
            model="kling-video",
            interface="video_to_video_multipart",
            capabilities=("video_to_video",),
        )

        # 1. Plain mock
        mock_opener = MagicMock()
        with pytest.raises(video_ai_edit_provider.AiEditProviderError):
            video_ai_edit_provider.submit_video_edit(
                cfg,
                source_video_path=str(sample_video),
                prompt="prompt",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="test-7-mock",
                submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
                opener=mock_opener,
            )
        assert mock_opener.call_count == 0

        # 2. Plain callable
        calls = []

        def callable_transport(*args, **kwargs):
            calls.append(args)

        with pytest.raises(video_ai_edit_provider.AiEditProviderError):
            video_ai_edit_provider.submit_video_edit(
                cfg,
                source_video_path=str(sample_video),
                prompt="prompt",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="test-7-callable",
                submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
                opener=callable_transport,
            )
        assert len(calls) == 0


# ---------------------------------------------------------------------------
# 8. Text2video V2V mismatch fails closed
# ---------------------------------------------------------------------------

def test_8_key4u_text2video_remains_blocked(tmp_path: Path):
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

    mock_opener = MagicMock()
    with pytest.raises(video_ai_edit_provider.AiEditProviderError) as exc_info:
        video_ai_edit_provider.submit_video_edit(
            cfg,
            source_video_path=str(sample_video),
            prompt="cinematic edit",
            negative_prompt="",
            aspect_ratio="9:16",
            duration_seconds=5,
            job_id="test-job-8",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=mock_opener,
        )
    assert exc_info.value.reason == "provider_capability_contract_mismatch"
    assert mock_opener.call_count == 0


# ---------------------------------------------------------------------------
# 9. Image2video V2V mismatch fails closed
# ---------------------------------------------------------------------------

def test_9_key4u_image2video_remains_blocked_for_v2v(tmp_path: Path):
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
            job_id="test-job-9",
            submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
            public_user_confirmed=True,
            opener=mock_opener,
        )
    assert exc_info.value.reason == "provider_capability_contract_mismatch"
    assert mock_opener.call_count == 0


# ---------------------------------------------------------------------------
# 10. Model catalog capability alone is insufficient
# ---------------------------------------------------------------------------

def test_10_model_catalog_v2v_capability_alone_is_insufficient():
    """Catalog metadata declaring video_to_video capability is insufficient without proven wire contract."""
    contract = video_ai_edit_provider.model_contract("key4u_video", "kling-video")
    assert contract.get("known") is True
    assert contract.get("video_to_video") is True

    # Declarations check
    assert video_ai_edit_provider.CURRENT_KEY4U_MULTIPART_V2V_ADAPTER_PROVEN is False
    assert video_ai_edit_provider.ALL_KEY4U_V2V_GLOBALLY_DECLARED_UNAVAILABLE is False
    assert video_ai_edit_provider.MOTION_CONTROL_AUTO_ENABLED is False
    assert video_ai_edit_provider.MOTION_CONTROL_REUSED_AS_MULTIPART is False
    assert video_ai_edit_provider.UNVERIFIED_V2V_ENDPOINT_INVENTED is False

    # Wire contract must be False
    assert not video_ai_edit_provider.has_proven_v2v_wire_contract(
        "key4u_video", "kling-video", "https://api.key4u.click/kling/v1/videos/text2video"
    )
    assert not video_ai_edit_provider.has_proven_v2v_wire_contract(
        "key4u_video", "kling-video", "https://api.key4u.click/kling/v1/videos/image2video"
    )
    assert not video_ai_edit_provider.has_proven_v2v_wire_contract(
        "key4u_video", "kling-video", "https://api.key4u.click/custom/unverified/endpoint"
    )


# ---------------------------------------------------------------------------
# 11. SelfShot2 mismatch makes zero HTTP calls
# ---------------------------------------------------------------------------

def test_11_selfshot2_mismatch_fails_before_provider_http(tmp_path: Path):
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
# 12. SelfShot3 mismatch makes zero HTTP calls
# ---------------------------------------------------------------------------

def test_12_selfshot3_mismatch_fails_before_provider_http(tmp_path: Path):
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
# 13. Mismatch cannot trigger secondary provider fallback
# ---------------------------------------------------------------------------

def test_13_no_fallback_after_primary_capability_mismatch(tmp_path: Path):
    """Primary capability mismatch strictly prevents fallback to secondary provider."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"TEST_VIDEO_BYTES_NO_FALLBACK")

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
# 14. Tier 500 duration contract is preserved
# ---------------------------------------------------------------------------

def test_14_tier_500_duration_preserved():
    """Tier 500 duration contract is exactly 5 seconds."""
    route = video_ai_real_pricing.product_video_route_by_tier(500)
    assert route["seconds_per_scene"] == 5
    assert route["tier_id"] == 500


# ---------------------------------------------------------------------------
# 15. Source segment missing / unbound -> FAIL_CLOSED
# ---------------------------------------------------------------------------

def test_15_unbound_missing_source_fails_closed(tmp_path: Path):
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
# 16. Text-only fallback -> FORBIDDEN
# ---------------------------------------------------------------------------

def test_16_text_only_fallback_forbidden(tmp_path: Path):
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

    with patch("services.video_real_render_connector._selfshot2_provider_configs", return_value=[mock_cfg]), \
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


# ---------------------------------------------------------------------------
# 17. Internal test harness URL cannot become production V2V authority
# ---------------------------------------------------------------------------

def test_17_internal_test_harness_url_cannot_become_production_v2v_authority():
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
# 18. Same test harness URL cannot prove V2V for Key4U
# ---------------------------------------------------------------------------

def test_18_same_url_cannot_prove_v2v_for_key4u(tmp_path: Path):
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
# 19. Same test harness URL cannot prove V2V for generic provider
# ---------------------------------------------------------------------------

def test_19_same_url_cannot_prove_v2v_for_generic_provider(tmp_path: Path):
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
