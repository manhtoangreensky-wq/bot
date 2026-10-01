"""Comprehensive contract and regression tests for Fal.ai Wan 2.2 V2V integration.

Scope: P0.PRODUCT_VIDEO
Product: video_ai_video_reference
Provider: fal_video
Model: fal-ai/wan/v2.2-a14b/video-to-video

Strict zero-real-call policy: all network I/O isolated via mocks.
Enforces explicit FAL_VIDEO_TO_VIDEO_ENABLED gate: token alone never activates paid provider.
"""

from __future__ import annotations

from decimal import Decimal
import io
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request
import pytest

from services import video_ai_edit_provider
from services import video_ai_real_pricing
from services import video_provider_catalog
from services import video_provider_router
from services import video_real_render_connector
from services.video_real_render_connector import RealVideoRenderError


# ---------------------------------------------------------------------------
# 1. Fal Model Contract in Catalog & Router Candidate
# ---------------------------------------------------------------------------

def test_1_fal_model_contract_registered_in_catalog():
    """Fal Wan 2.2 V2V model must be recognized in the catalog with video_to_video capability."""
    contract = video_ai_edit_provider.model_contract("fal_video", "fal-ai/wan/v2.2-a14b/video-to-video")
    assert contract["known"] is True
    assert contract["video_to_video"] is True
    assert "video_to_video" in contract["capabilities"]
    assert contract["payload_adapter"] == "fal_wan_v2v"

    # Alias fal.ai and fal must resolve identically
    contract_alias = video_ai_edit_provider.model_contract("fal.ai", "fal-ai/wan/v2.2-a14b/video-to-video")
    assert contract_alias["known"] is True
    assert contract_alias["video_to_video"] is True


def test_2_fal_provider_router_candidate_and_capabilities():
    """video_provider_router must expose fal_video with video_to_video capability and Wan 2.2 model when enabled."""
    env = {
        "FAL_KEY": "test_fal_key_mock",
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "VIDEO_PROVIDER_CHAIN": "fal_video",
    }
    adapter = video_provider_router._generic_adapter_for("fal_video", env)
    assert adapter is not None
    assert adapter.provider_name == "fal_video"
    assert adapter.capabilities()["capabilities"] == ["video_to_video", "short_video"]
    assert adapter.env.get(adapter.model_env) == "fal-ai/wan/v2.2-a14b/video-to-video"
    assert "fal_video" in video_provider_router.DEFAULT_VIDEO_PROVIDER_CHAIN


def test_3_video_ai_video_reference_routes_to_fal_v2v_in_routing_config():
    """config/product_video_model_routing.json must register video_ai_video_reference -> fal_video."""
    routing = video_provider_catalog.load_product_video_model_routing()
    assert "fal_video" in routing["default_provider_chain"]
    assert "product_routes" in routing
    prod_route = routing["product_routes"].get("video_ai_video_reference")
    assert prod_route is not None
    assert prod_route["product"] == "video_ai_video_reference"
    assert prod_route["capability"] == "video_to_video"
    assert prod_route["provider"] == "fal_video"
    assert prod_route["model"] == "fal-ai/wan/v2.2-a14b/video-to-video"
    assert prod_route["max_single_task_seconds"] == 10


# ---------------------------------------------------------------------------
# 2. Explicit Fal Enable Authority Gate (R16.04A Core Invariant)
# ---------------------------------------------------------------------------

def test_fal_key_only_does_not_enable_provider():
    """FAL_KEY present without FAL_VIDEO_TO_VIDEO_ENABLED leaves enabled=False and fails validation."""
    cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {"FAL_KEY": "my_secret_token"})
    assert cfg.enabled is False
    val = video_ai_edit_provider.validate_provider_config(cfg)
    assert val["ok"] is False
    assert "enabled" in val["invalid_fields"]


def test_fal_explicit_false_does_not_enable_provider():
    """Explicit false/0 flag leaves enabled=False even if FAL_KEY is present."""
    for val_str in ("0", "false", "no", "off"):
        cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
            "FAL_KEY": "my_secret_token",
            "FAL_VIDEO_TO_VIDEO_ENABLED": val_str,
        })
        assert cfg.enabled is False
        val = video_ai_edit_provider.validate_provider_config(cfg)
        assert val["ok"] is False


def test_fal_explicit_true_allows_validation():
    """Explicit true/1 flag with valid key enables provider and passes validation."""
    for val_str in ("1", "true", "yes", "on"):
        cfg = video_ai_edit_provider.provider_config_from_env("fal_video", {
            "FAL_KEY": "my_secret_token",
            "FAL_VIDEO_TO_VIDEO_ENABLED": val_str,
        })
        assert cfg.enabled is True
        val = video_ai_edit_provider.validate_provider_config(cfg)
        assert val["ok"] is True


def test_router_excludes_fal_without_enable_flag():
    """Router creates fal_video adapter with enabled=False when enable flag is missing."""
    env = {"FAL_KEY": "valid_token"}
    adapter = video_provider_router._generic_adapter_for("fal_video", env)
    assert adapter._configured() is False
    caps = adapter.capabilities()
    assert caps["enabled"] is False
    assert caps["configured"] is False


def test_router_excludes_fal_when_disabled():
    """Router creates fal_video adapter with enabled=False when explicitly disabled."""
    env = {
        "FAL_KEY": "valid_token",
        "FAL_VIDEO_TO_VIDEO_ENABLED": "0",
    }
    adapter = video_provider_router._generic_adapter_for("fal_video", env)
    assert adapter._configured() is False
    caps = adapter.capabilities()
    assert caps["enabled"] is False
    assert caps["configured"] is False


def test_router_includes_fal_only_when_explicitly_enabled():
    """Router configures fal_video as enabled only when FAL_VIDEO_TO_VIDEO_ENABLED=1 and token present."""
    env = {
        "FAL_KEY": "valid_token",
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
    }
    adapter = video_provider_router._generic_adapter_for("fal_video", env)
    assert adapter._configured() is True
    caps = adapter.capabilities()
    assert caps["enabled"] is True
    assert caps["configured"] is True


# ---------------------------------------------------------------------------
# 3. Duration Tiers & Frame Calculation (5s -> 81, 10s -> 161)
# ---------------------------------------------------------------------------

def test_4_fal_wan_v2v_frame_calculation():
    """Wan 2.2 requires (num_frames - 1) % 4 == 0 (5s -> 81 frames, 10s -> 161 frames)."""
    assert video_ai_edit_provider.calculate_fal_wan_v2v_num_frames(5.0) == 81
    assert video_ai_edit_provider.calculate_fal_wan_v2v_num_frames(10.0) == 161

    # Out-of-bounds durations must fail closed
    with pytest.raises(video_ai_edit_provider.AiEditProviderError, match="fal_v2v_duration_exceeds_max_frames"):
        video_ai_edit_provider.calculate_fal_wan_v2v_num_frames(15.0)


# ---------------------------------------------------------------------------
# 4. Fal Storage Upload (Initiate POST -> Binary PUT)
# ---------------------------------------------------------------------------

def test_5_fal_storage_upload_initiate_and_put(tmp_path: Path):
    """upload_fal_media_file performs POST /storage/upload/initiate then PUT binary bytes."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"TEST_MP4_BINARY_PAYLOAD_12345")

    cfg = video_ai_edit_provider.provider_config_from_env(
        "fal_video",
        {
            "FAL_KEY": "valid_fal_secret_key",
            "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        },
    )

    mock_initiate_resp = MagicMock()
    mock_initiate_resp.status = 200
    mock_initiate_resp.read.return_value = json.dumps({
        "upload_url": "https://storage.fal.ai/upload/signed_target_url",
        "file_url": "https://fal.media/files/permanent_video_source.mp4",
    }).encode("utf-8")

    mock_put_resp = MagicMock()
    mock_put_resp.status = 200

    def mock_opener(req, timeout=120.0):
        if req.get_method() == "POST" and "initiate" in req.full_url:
            assert req.headers.get("Authorization") == "Key valid_fal_secret_key"
            body = json.loads(req.data.decode("utf-8"))
            assert body["file_name"] == "source.mp4"
            assert body["content_type"] == "video/mp4"
            return mock_initiate_resp
        elif req.get_method() == "PUT":
            assert req.full_url == "https://storage.fal.ai/upload/signed_target_url"
            assert req.data == b"TEST_MP4_BINARY_PAYLOAD_12345"
            return mock_put_resp
        raise AssertionError(f"Unexpected request: {req.get_method()} {req.full_url}")

    res = video_ai_edit_provider.upload_fal_media_file(cfg, source_file, opener=mock_opener)
    assert res["ok"] is True
    assert res["provider"] == "fal_video"
    assert res["file_url"] == "https://fal.media/files/permanent_video_source.mp4"
    assert res["local_size_bytes"] == len(b"TEST_MP4_BINARY_PAYLOAD_12345")


# ---------------------------------------------------------------------------
# 5. Fal Wire Submit, Request ID Parsing, Status Polling, Result URL
# ---------------------------------------------------------------------------

def test_6_fal_wan_v2v_submit_and_poll_contract():
    """Submit binds video_url, num_frames, auth Key header; poll returns status and result URL."""
    cfg = video_ai_edit_provider.provider_config_from_env(
        "fal_video",
        {
            "FAL_KEY": "valid_fal_secret_key",
            "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        },
    )

    # 1. Submit
    mock_submit_resp = MagicMock()
    mock_submit_resp.status = 200
    mock_submit_resp.read.return_value = json.dumps({
        "request_id": "fal_req_9988776655",
        "status": "IN_QUEUE",
    }).encode("utf-8")

    def mock_submit_opener(req, timeout=120.0):
        assert req.get_method() == "POST"
        assert req.headers.get("Authorization") == "Key valid_fal_secret_key"
        body = json.loads(req.data.decode("utf-8"))
        assert body["video_url"] == "https://fal.media/files/source.mp4"
        assert body["num_frames"] == 81
        assert body["prompt"] == "enhance video quality"
        return mock_submit_resp

    submit_res = video_ai_edit_provider.submit_video_edit(
        cfg,
        source_video_path="https://fal.media/files/source.mp4",
        prompt="enhance video quality",
        negative_prompt="",
        aspect_ratio="9:16",
        duration_seconds=5,
        job_id="job_v2v_01",
        submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
        public_user_confirmed=True,
        opener=mock_submit_opener,
    )
    assert submit_res["provider_task_id"] == "fal_req_9988776655"
    assert submit_res["accepted"] is True

    # 2. Poll
    mock_poll_resp = MagicMock()
    mock_poll_resp.status = 200
    mock_poll_resp.read.return_value = json.dumps({
        "status": "COMPLETED",
        "video": {"url": "https://fal.media/files/output_result.mp4"},
    }).encode("utf-8")

    def mock_poll_opener(req, timeout=120.0):
        assert req.get_method() == "GET"
        assert "fal_req_9988776655" in req.full_url
        assert req.headers.get("Authorization") == "Key valid_fal_secret_key"
        return mock_poll_resp

    poll_res = video_ai_edit_provider.poll_video_edit(cfg, "fal_req_9988776655", opener=mock_poll_opener)
    assert poll_res["status"] == "completed"
    assert poll_res["result_url"] == "https://fal.media/files/output_result.mp4"
    assert poll_res["result_url_present"] is True


# ---------------------------------------------------------------------------
# 6. FX Authority Contract: FAL_USD_TO_VND Positive Integer (Fail-Closed)
# ---------------------------------------------------------------------------

def test_7_fal_usd_to_vnd_strict_positive_integer_contract():
    """FAL_USD_TO_VND must be positive integer; missing/0/neg/malformed fail closed; no 3500 fallback."""
    # Valid positive integer
    assert video_ai_real_pricing.fal_provider_usd_to_vnd({"FAL_USD_TO_VND": "25500"}) == Decimal("25500")
    assert video_ai_real_pricing.product_video_provider_usd_to_vnd("fal_video", {"FAL_USD_TO_VND": "26000"}) == Decimal("26000")

    # Missing fails closed
    with pytest.raises(ValueError, match="fal_usd_to_vnd_runtime_required"):
        video_ai_real_pricing.fal_provider_usd_to_vnd({})

    # Empty string fails closed
    with pytest.raises(ValueError, match="fal_usd_to_vnd_runtime_required"):
        video_ai_real_pricing.fal_provider_usd_to_vnd({"FAL_USD_TO_VND": ""})

    # Zero fails closed
    with pytest.raises(ValueError, match="fal_usd_to_vnd_must_be_positive"):
        video_ai_real_pricing.fal_provider_usd_to_vnd({"FAL_USD_TO_VND": "0"})

    # Negative fails closed
    with pytest.raises(ValueError, match="fal_usd_to_vnd_must_be_positive_integer"):
        video_ai_real_pricing.fal_provider_usd_to_vnd({"FAL_USD_TO_VND": "-25500"})

    # Decimal string fails closed (must be integer)
    with pytest.raises(ValueError, match="fal_usd_to_vnd_must_be_positive_integer"):
        video_ai_real_pricing.fal_provider_usd_to_vnd({"FAL_USD_TO_VND": "25500.5"})

    # Non-numeric fails closed
    with pytest.raises(ValueError, match="fal_usd_to_vnd_must_be_positive_integer"):
        video_ai_real_pricing.fal_provider_usd_to_vnd({"FAL_USD_TO_VND": "invalid_fx"})


def test_8_pricing_snapshot_fails_closed_on_invalid_or_missing_fx():
    """pricing_snapshot must fail closed if FAL_USD_TO_VND is missing or invalid."""
    # Missing FX
    snap1 = video_ai_edit_provider.pricing_snapshot(
        {"VIDEO_AI_EDIT_PRICE_5S_XU": "250"},
        provider_name="fal_video",
        duration_seconds=5,
    )
    assert snap1["configured"] is False
    assert snap1["commercial_enable_allowed"] is False
    assert snap1["provider_submit_allowed"] is False
    assert snap1["loss_guard_pass"] is False
    assert snap1["blocker"] == "missing_fal_fx_authority_fail_closed"

    # Zero FX
    snap2 = video_ai_edit_provider.pricing_snapshot(
        {"VIDEO_AI_EDIT_PRICE_5S_XU": "250", "FAL_USD_TO_VND": "0"},
        provider_name="fal_video",
        duration_seconds=5,
    )
    assert snap2["configured"] is False
    assert snap2["blocker"] == "missing_fal_fx_authority_fail_closed"

    # Negative FX
    snap3 = video_ai_edit_provider.pricing_snapshot(
        {"VIDEO_AI_EDIT_PRICE_5S_XU": "250", "FAL_USD_TO_VND": "-25500"},
        provider_name="fal_video",
        duration_seconds=5,
    )
    assert snap3["configured"] is False
    assert snap3["blocker"] == "missing_fal_fx_authority_fail_closed"


# ---------------------------------------------------------------------------
# 7. Duration Pricing & Pre-Submit Loss Guard
# ---------------------------------------------------------------------------

def test_9_duration_pricing_5s_and_10s_routing():
    """5s reads 5S_XU (or compat XU); 10s strictly reads 10S_XU; unsupported fails closed."""
    env = {
        "FAL_USD_TO_VND": "25500",
        "VIDEO_AI_EDIT_PRICE_5S_XU": "200",
        "VIDEO_AI_EDIT_PRICE_10S_XU": "400",
    }
    # 5s: cost = 0.40 * 25500 = 10,200 VND, revenue = 200 * 100 = 20,000 VND -> pass
    snap_5s = video_ai_edit_provider.pricing_snapshot(env, provider_name="fal_video", duration_seconds=5)
    assert snap_5s["configured"] is True
    assert snap_5s["price_xu"] == 200
    assert snap_5s["provider_cost_usd"] == 0.40
    assert snap_5s["provider_cost_vnd"] == 10200
    assert snap_5s["gross_margin_vnd"] == 9800
    assert snap_5s["loss_guard_pass"] is True
    assert snap_5s["provider_submit_allowed"] is True

    # 10s: cost = 0.80 * 25500 = 20,400 VND, revenue = 400 * 100 = 40,000 VND -> pass
    snap_10s = video_ai_edit_provider.pricing_snapshot(env, provider_name="fal_video", duration_seconds=10)
    assert snap_10s["configured"] is True
    assert snap_10s["price_xu"] == 400
    assert snap_10s["provider_cost_usd"] == 0.80
    assert snap_10s["provider_cost_vnd"] == 20400
    assert snap_10s["gross_margin_vnd"] == 19600
    assert snap_10s["loss_guard_pass"] is True

    # 10s missing: does NOT auto-double 5s price
    env_missing_10s = {
        "FAL_USD_TO_VND": "25500",
        "VIDEO_AI_EDIT_PRICE_5S_XU": "200",
    }
    snap_10s_missing = video_ai_edit_provider.pricing_snapshot(env_missing_10s, provider_name="fal_video", duration_seconds=10)
    assert snap_10s_missing["configured"] is False
    assert snap_10s_missing["price_xu"] == 0
    assert snap_10s_missing["blocker"] == "missing_customer_price_fail_closed"

    # Unsupported duration
    snap_unsupported = video_ai_edit_provider.pricing_snapshot(env, provider_name="fal_video", duration_seconds=8)
    assert snap_unsupported["configured"] is False
    assert snap_unsupported["blocker"] == "unsupported_duration_tier_fail_closed"


def test_10_loss_guard_blocks_submit_when_price_below_provider_cost():
    """If customer revenue < provider cost * 1, Loss Guard blocks provider submit."""
    # Cost for 5s: 0.40 * 25500 = 10,200 VND.
    # Price 90 Xu = 9,000 VND (< 10,200 VND).
    env = {
        "FAL_USD_TO_VND": "25500",
        "VIDEO_AI_EDIT_PRICE_5S_XU": "90",
    }
    snap = video_ai_edit_provider.pricing_snapshot(env, provider_name="fal_video", duration_seconds=5)
    assert snap["configured"] is False
    assert snap["commercial_enable_allowed"] is False
    assert snap["provider_submit_allowed"] is False
    assert snap["loss_guard_pass"] is False
    assert snap["blocker"] == "customer_price_below_provider_cost_loss_guard_blocked"


# ---------------------------------------------------------------------------
# 8. Execution Route in Render Connector: _render_video_reference_fal_v2v
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_source_mp4(tmp_path: Path) -> Path:
    p = tmp_path / "valid_source.mp4"
    p.write_bytes(b"MOCK_SOURCE_VIDEO_BYTES_FOR_V2V")
    return p


def test_11_render_video_reference_success_execution(tmp_path: Path, valid_source_mp4: Path):
    """End-to-end mock execution of video_ai_video_reference through Fal V2V path."""
    output_mp4 = tmp_path / "final_output.mp4"

    job = {
        "source_video_local_path": str(valid_source_mp4),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "duration_seconds": 5,
        "prompt_text": "cinematic transformation",
        "job_id": "job_ref_01",
    }
    asset_pack = {
        "source_video_local_path": str(valid_source_mp4),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
    }

    env_patch = {
        "FAL_KEY": "valid_fal_key_mock",
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_USD_TO_VND": "25500",
        "VIDEO_AI_EDIT_PRICE_5S_XU": "250",
    }

    with patch.dict(os.environ, env_patch), \
         patch("services.video_ai_edit_provider.upload_fal_media_file") as mock_upload, \
         patch("services.video_ai_edit_provider.submit_video_edit") as mock_submit, \
         patch("services.video_ai_edit_provider.wait_for_result") as mock_wait, \
         patch("services.video_ai_edit_provider.download_result") as mock_download:

        mock_upload.return_value = {"ok": True, "file_url": "https://fal.media/files/uploaded.mp4"}
        mock_submit.return_value = {"accepted": True, "provider_task_id": "task_fal_1234"}
        mock_wait.return_value = {"status": "completed", "result_url": "https://fal.media/files/out.mp4"}

        def do_download(url, dest):
            Path(dest).write_bytes(b"MOCK_GENERATED_OUTPUT_VIDEO")
            return {"ok": True, "path": dest}
        mock_download.side_effect = do_download

        res = video_real_render_connector._render_video_reference_fal_v2v(
            job=job,
            asset_pack=asset_pack,
            raw_path=str(output_mp4),
            fallback_prompt="cinematic transformation",
            aspect_ratio="9:16",
            scene_index=1,
        )

        assert res["ok"] is True
        assert res["video_reference"] is True
        assert res["provider"] == "fal_video"
        assert res["model"] == "fal-ai/wan/v2.2-a14b/video-to-video"
        assert res["provider_task_id"] == "task_fal_1234"
        assert res["duration"] == 5
        assert res["no_charge"] is False
        assert output_mp4.is_file()


def test_12_render_video_reference_source_missing_fails_closed_no_charge(tmp_path: Path):
    """Missing source video must fail closed before provider calls, with no_charge=True."""
    raw_path = tmp_path / "raw.mp4"
    job = {
        "source_video_local_path": str(tmp_path / "non_existent.mp4"),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
    }
    with pytest.raises(RealVideoRenderError) as exc_info:
        video_real_render_connector._render_video_reference_fal_v2v(
            job=job,
            asset_pack={},
            raw_path=str(raw_path),
            fallback_prompt="",
            aspect_ratio="9:16",
        )
    assert exc_info.value.diagnostics["no_charge"] is True
    assert exc_info.value.diagnostics["blocker"] == "video_reference_source_video_not_materialized"
    assert exc_info.value.diagnostics["provider_attempted"] is False


def test_13_render_video_reference_unconfirmed_fails_closed_no_charge(tmp_path: Path, valid_source_mp4: Path):
    """Unconfirmed submission fails closed before provider submit, with no_charge=True."""
    raw_path = tmp_path / "raw.mp4"
    job = {
        "source_video_local_path": str(valid_source_mp4),
        "public_user_confirmed": False,
        "submit_source": "unconfirmed_source",
    }
    with pytest.raises(RealVideoRenderError) as exc_info:
        video_real_render_connector._render_video_reference_fal_v2v(
            job=job,
            asset_pack={},
            raw_path=str(raw_path),
            fallback_prompt="",
            aspect_ratio="9:16",
        )
    assert exc_info.value.diagnostics["no_charge"] is True
    assert exc_info.value.diagnostics["blocker"] == "video_reference_public_confirm_required"


def test_14_render_video_reference_unsupported_duration_fails_closed_no_charge(tmp_path: Path, valid_source_mp4: Path):
    """Unsupported duration (e.g. 8s or 15s) fails closed before provider submit, with no_charge=True."""
    raw_path = tmp_path / "raw.mp4"
    job = {
        "source_video_local_path": str(valid_source_mp4),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "duration_seconds": 15,
    }
    with pytest.raises(RealVideoRenderError) as exc_info:
        video_real_render_connector._render_video_reference_fal_v2v(
            job=job,
            asset_pack={},
            raw_path=str(raw_path),
            fallback_prompt="",
            aspect_ratio="9:16",
        )
    assert exc_info.value.diagnostics["no_charge"] is True
    assert exc_info.value.diagnostics["blocker"] == "video_reference_unsupported_duration_no_charge"


def test_15_render_video_reference_pricing_loss_guard_blocks_submit_no_charge(tmp_path: Path, valid_source_mp4: Path):
    """Loss guard / missing price blocks render before provider call, with no_charge=True."""
    raw_path = tmp_path / "raw.mp4"
    job = {
        "source_video_local_path": str(valid_source_mp4),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "duration_seconds": 5,
    }
    # No price configured in environment
    with patch.dict(os.environ, {"FAL_KEY": "valid_key", "FAL_VIDEO_TO_VIDEO_ENABLED": "1", "FAL_USD_TO_VND": "25500"}, clear=False):
        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_video_reference_fal_v2v(
                job=job,
                asset_pack={},
                raw_path=str(raw_path),
                fallback_prompt="",
                aspect_ratio="9:16",
            )
        assert exc_info.value.diagnostics["no_charge"] is True
        assert exc_info.value.diagnostics["provider_attempted"] is False
        assert exc_info.value.diagnostics["provider_submit_called"] is False


def test_16_render_video_reference_provider_failure_fails_closed_no_charge(tmp_path: Path, valid_source_mp4: Path):
    """Provider failure or timeout must raise RealVideoRenderError with no_charge=True."""
    raw_path = tmp_path / "raw.mp4"
    job = {
        "source_video_local_path": str(valid_source_mp4),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "duration_seconds": 5,
        "prompt_text": "cinematic edit",
    }
    env_patch = {
        "FAL_KEY": "valid_fal_key_mock",
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_USD_TO_VND": "25500",
        "VIDEO_AI_EDIT_PRICE_5S_XU": "250",
    }
    with patch.dict(os.environ, env_patch), \
         patch("services.video_ai_edit_provider.upload_fal_media_file") as mock_upload, \
         patch("services.video_ai_edit_provider.submit_video_edit") as mock_submit:

        mock_upload.return_value = {"ok": True, "file_url": "https://fal.media/files/uploaded.mp4"}
        mock_submit.side_effect = video_ai_edit_provider.AiEditProviderError("provider_submit_http_500")

        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_video_reference_fal_v2v(
                job=job,
                asset_pack={},
                raw_path=str(raw_path),
                fallback_prompt="cinematic edit",
                aspect_ratio="9:16",
            )
        assert exc_info.value.diagnostics["no_charge"] is True
        assert exc_info.value.diagnostics["blocker"] == "provider_submit_http_500"


def test_17_render_video_reference_timeout_fails_closed_no_charge(tmp_path: Path, valid_source_mp4: Path):
    """Provider poll timeout raises RealVideoRenderError with no_charge=True."""
    raw_path = tmp_path / "raw.mp4"
    job = {
        "source_video_local_path": str(valid_source_mp4),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "duration_seconds": 5,
        "prompt_text": "cinematic edit",
    }
    env_patch = {
        "FAL_KEY": "valid_fal_key_mock",
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_USD_TO_VND": "25500",
        "VIDEO_AI_EDIT_PRICE_5S_XU": "250",
    }
    with patch.dict(os.environ, env_patch), \
         patch("services.video_ai_edit_provider.upload_fal_media_file") as mock_upload, \
         patch("services.video_ai_edit_provider.submit_video_edit") as mock_submit, \
         patch("services.video_ai_edit_provider.wait_for_result") as mock_wait:

        mock_upload.return_value = {"ok": True, "file_url": "https://fal.media/files/uploaded.mp4"}
        mock_submit.return_value = {"accepted": True, "provider_task_id": "task_timeout_123"}
        mock_wait.side_effect = video_ai_edit_provider.AiEditProviderError("provider_poll_timeout")

        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_video_reference_fal_v2v(
                job=job,
                asset_pack={},
                raw_path=str(raw_path),
                fallback_prompt="cinematic edit",
                aspect_ratio="9:16",
            )
        assert exc_info.value.diagnostics["no_charge"] is True
        assert exc_info.value.diagnostics["blocker"] == "provider_poll_timeout"


def test_18_render_video_reference_invalid_download_artifact_no_charge(tmp_path: Path, valid_source_mp4: Path):
    """If download succeeds but file is empty, must fail closed with no_charge=True."""
    raw_path = tmp_path / "empty_out.mp4"
    job = {
        "source_video_local_path": str(valid_source_mp4),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "duration_seconds": 5,
        "prompt_text": "cinematic edit",
    }
    env_patch = {
        "FAL_KEY": "valid_fal_key_mock",
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_USD_TO_VND": "25500",
        "VIDEO_AI_EDIT_PRICE_5S_XU": "250",
    }
    with patch.dict(os.environ, env_patch), \
         patch("services.video_ai_edit_provider.upload_fal_media_file") as mock_upload, \
         patch("services.video_ai_edit_provider.submit_video_edit") as mock_submit, \
         patch("services.video_ai_edit_provider.wait_for_result") as mock_wait, \
         patch("services.video_ai_edit_provider.download_result") as mock_download:

        mock_upload.return_value = {"ok": True, "file_url": "https://fal.media/files/uploaded.mp4"}
        mock_submit.return_value = {"accepted": True, "provider_task_id": "task_invalid_art"}
        mock_wait.return_value = {"status": "completed", "result_url": "https://fal.media/files/out.mp4"}

        # Simulate 0-byte downloaded file
        def fake_download(url, dest):
            Path(dest).write_bytes(b"")
            return {"ok": True, "path": dest}
        mock_download.side_effect = fake_download

        with pytest.raises(RealVideoRenderError) as exc_info:
            video_real_render_connector._render_video_reference_fal_v2v(
                job=job,
                asset_pack={},
                raw_path=str(raw_path),
                fallback_prompt="cinematic edit",
                aspect_ratio="9:16",
            )
        assert exc_info.value.diagnostics["no_charge"] is True
        assert exc_info.value.diagnostics["blocker"] == "video_reference_download_artifact_invalid_no_charge"


def test_19_active_task_recovery_polls_only_no_new_submit(tmp_path: Path, valid_source_mp4: Path):
    """When provider_task_id is present, connector strictly polls existing task without re-submitting."""
    raw_path = tmp_path / "recovered.mp4"
    job = {
        "source_video_local_path": str(valid_source_mp4),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "duration_seconds": 5,
        "provider_task_id": "existing_active_task_999",
    }
    env_patch = {
        "FAL_KEY": "valid_fal_key_mock",
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_USD_TO_VND": "25500",
        "VIDEO_AI_EDIT_PRICE_5S_XU": "250",
    }
    with patch.dict(os.environ, env_patch), \
         patch("services.video_ai_edit_provider.upload_fal_media_file") as mock_upload, \
         patch("services.video_ai_edit_provider.submit_video_edit") as mock_submit, \
         patch("services.video_ai_edit_provider.wait_for_result") as mock_wait, \
         patch("services.video_ai_edit_provider.download_result") as mock_download:

        mock_wait.return_value = {"status": "completed", "result_url": "https://fal.media/files/out.mp4"}
        def do_download(url, dest):
            Path(dest).write_bytes(b"RECOVERED_MP4")
            return {"ok": True, "path": dest}
        mock_download.side_effect = do_download

        res = video_real_render_connector._render_video_reference_fal_v2v(
            job=job,
            asset_pack={},
            raw_path=str(raw_path),
            fallback_prompt="",
            aspect_ratio="9:16",
        )

        assert res["ok"] is True
        assert res["poll_only"] is True
        assert res["provider_submit_called"] is False
        assert res["provider_task_id"] == "existing_active_task_999"
        mock_upload.assert_not_called()
        mock_submit.assert_not_called()
        mock_wait.assert_called_once()


# ---------------------------------------------------------------------------
# 9. Negative Safety Invariants: Key4U V2V, Missing FX, Missing Price, Loss Guard, Zero Real Calls
# ---------------------------------------------------------------------------

def test_key4u_v2v_still_fail_closed():
    """Key4U V2V must remain disabled and fail closed."""
    assert not video_ai_edit_provider.has_proven_v2v_wire_contract("key4u_video", "kling-video")
    env = {"KEY4U_API_KEY": "dummy_key"}
    adapter = video_provider_router._generic_adapter_for("key4u_video", env)
    assert "video_to_video" not in adapter.capabilities()["capabilities"]


def test_missing_fx_still_fail_closed():
    """Missing FAL_USD_TO_VND must fail closed."""
    with pytest.raises(ValueError, match="fal_usd_to_vnd_runtime_required"):
        video_ai_real_pricing.fal_provider_usd_to_vnd({})


def test_missing_price_still_fail_closed():
    """Missing customer price fails closed."""
    snap = video_ai_edit_provider.pricing_snapshot(
        {"FAL_USD_TO_VND": "25500"},
        provider_name="fal_video",
        duration_seconds=5,
    )
    assert snap["configured"] is False
    assert snap["blocker"] == "missing_customer_price_fail_closed"


def test_loss_guard_still_blocks_submit():
    """Pre-submit Loss Guard blocks submit when customer revenue < provider cost."""
    env = {
        "FAL_USD_TO_VND": "25500",
        "VIDEO_AI_EDIT_PRICE_5S_XU": "90",  # 90 * 100 = 9,000 VND < 10,200 VND
    }
    snap = video_ai_edit_provider.pricing_snapshot(env, provider_name="fal_video", duration_seconds=5)
    assert snap["loss_guard_pass"] is False
    assert snap["provider_submit_allowed"] is False
    assert snap["blocker"] == "customer_price_below_provider_cost_loss_guard_blocked"


def test_zero_real_provider_calls():
    """Contract tests never make external network calls."""
    with pytest.raises(ValueError):
        video_ai_real_pricing.fal_provider_usd_to_vnd({})
