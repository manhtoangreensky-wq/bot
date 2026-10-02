"""Tests for Fal Wan 2.2 V2V Web Worker wire contract remediation (R16.09Q/R/R1).

Ensures local video fixtures are uploaded to Fal storage before model queue submit,
wire contract invariants (num_frames=81 for 5s, 16 fps, hosted https URL) are strictly
enforced via canonical build_fal_wan_v2v_payload, plain http is rejected fail-closed,
and upload/transport errors fail-closed with 0 retries and 0 wallet mutations.
"""

from __future__ import annotations

import io
import json
import os
import socket
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from providers.video_generic_http_provider import (
    GenericHttpVideoProvider,
    VideoProviderContractError,
    _build_provider_payload,
    _fal_wire_payload,
    build_fal_video_payload,
)
from services.video_ai_edit_provider import (
    AiEditProviderConfig,
    AiEditProviderError,
    build_fal_wan_v2v_payload,
    calculate_fal_wan_v2v_num_frames,
    upload_fal_media_file,
)
from services.video_provider_base import VideoGenerationRequest, VideoSubmitResult
from services.video_provider_router import _generic_adapter_for


@pytest.fixture
def mock_fal_env() -> dict[str, str]:
    return {
        "FAL_KEY": "fake_fal_test_key_12345678",
        "FAL_VIDEO_ENABLED": "1",
        "FAL_VIDEO_TO_VIDEO_ENABLED": "1",
        "FAL_VIDEO_MODEL": "fal-ai/wan/v2.2-a14b/video-to-video",
        "FAL_VIDEO_SUBMIT_URL": "https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
        "FAL_VIDEO_POLL_URL": "https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
        "FAL_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "FAL_VIDEO_AUTH_HEADER_VALUE": "Key fake_fal_test_key_12345678",
        "FAL_VIDEO_RESULT_FIELD": "video.url",
        "FAL_VIDEO_CAPABILITIES": "video_to_video,short_video",
    }


# ==============================================================================
# A. SOURCE VALIDATION & REJECTION TESTS
# ==============================================================================

def test_a01_frames_calculation_5s_equals_81():
    """Wan 2.2 frame formula requires (num_frames - 1) % 4 == 0 at 16 fps."""
    frames_5s = calculate_fal_wan_v2v_num_frames(5.0)
    assert frames_5s == 81
    assert (frames_5s - 1) % 4 == 0

    # Boundary checks
    assert calculate_fal_wan_v2v_num_frames(3.0) == 49
    assert (calculate_fal_wan_v2v_num_frames(3.0) - 1) % 4 == 0
    assert calculate_fal_wan_v2v_num_frames(0) == 81  # defaults to 5.0s / 81 frames


def test_a02_missing_source_path_model_submit_zero(mock_fal_env: dict[str, str]):
    """If source_video_path is missing for V2V, submit aborts immediately: MODEL_SUBMIT=0."""
    provider = _generic_adapter_for("fal_video", mock_fal_env)

    req = VideoGenerationRequest(
        job_id="test_job_123",
        product_type="video_ai_video_reference",
        prompt="transform scene",
        required_capability="video_to_video",
        source_video_path="",
        duration_seconds=5.0,
    )

    with patch.object(provider, "_open_json") as mock_open_json:
        result = provider.submit_video_job(req)

    assert mock_open_json.call_count == 0
    assert result.ok is False
    assert result.provider_status == "contract_blocked"
    assert result.error_code == "fal_v2v_source_video_path_missing"
    assert result.raw.get("no_charge") is True


def test_a03_plain_http_remote_url_fails_closed_before_submit(mock_fal_env: dict[str, str]):
    """Plain http:// remote source URL must be rejected fail-closed before model queue submit."""
    provider = _generic_adapter_for("fal_video", mock_fal_env)

    req = VideoGenerationRequest(
        job_id="test_job_123",
        product_type="video_ai_video_reference",
        prompt="transform scene",
        required_capability="video_to_video",
        source_video_path="http://insecure.site/video.mp4",
        duration_seconds=5.0,
    )

    with patch.object(provider, "_open_json") as mock_open_json:
        result = provider.submit_video_job(req)

    assert mock_open_json.call_count == 0
    assert result.ok is False
    assert result.provider_status == "contract_blocked"
    assert result.error_code == "fal_v2v_insecure_http_source_unsupported"
    assert result.raw.get("no_charge") is True


def test_a04_empty_local_file_fails_closed(tmp_path: Path, mock_fal_env: dict[str, str]):
    """Empty local file must raise fail-closed before initiate or model submit."""
    empty_file = tmp_path / "empty_scene.mp4"
    empty_file.write_bytes(b"")

    provider = _generic_adapter_for("fal_video", mock_fal_env)

    req = VideoGenerationRequest(
        job_id="test_job_123",
        product_type="video_ai_video_reference",
        prompt="transform scene",
        required_capability="video_to_video",
        source_video_path=str(empty_file),
        duration_seconds=5.0,
    )

    with patch.object(provider, "_open_json") as mock_open_json:
        result = provider.submit_video_job(req)

    assert mock_open_json.call_count == 0
    assert result.ok is False
    assert result.provider_status == "contract_blocked"
    assert result.error_code == "fal_scene_upload_file_empty"
    assert result.raw.get("no_charge") is True


def test_a05_unsupported_extension_fails_closed(tmp_path: Path, mock_fal_env: dict[str, str]):
    """Unsupported local extension (.txt) must raise fail-closed before initiate or model submit."""
    bad_file = tmp_path / "scene.txt"
    bad_file.write_bytes(b"not a video file")

    provider = _generic_adapter_for("fal_video", mock_fal_env)

    req = VideoGenerationRequest(
        job_id="test_job_123",
        product_type="video_ai_video_reference",
        prompt="transform scene",
        required_capability="video_to_video",
        source_video_path=str(bad_file),
        duration_seconds=5.0,
    )

    with patch.object(provider, "_open_json") as mock_open_json:
        result = provider.submit_video_job(req)

    assert mock_open_json.call_count == 0
    assert result.ok is False
    assert result.provider_status == "contract_blocked"
    assert result.error_code == "fal_scene_upload_unsupported_media_type"


def test_a06_already_remote_https_video_url_does_not_call_storage(mock_fal_env: dict[str, str]):
    """If source_video_path is already https://, storage upload must be skipped and model called."""
    existing_remote_url = "https://fal.media/files/already_uploaded.mp4"
    provider = _generic_adapter_for("fal_video", mock_fal_env)

    req = VideoGenerationRequest(
        job_id="test_job_123",
        product_type="video_ai_video_reference",
        prompt="cyberpunk style",
        required_capability="video_to_video",
        source_video_path=existing_remote_url,
        duration_seconds=5.0,
    )

    submitted_payload: dict[str, Any] = {}

    def fake_open_json(url: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        nonlocal submitted_payload
        submitted_payload = dict(payload or {})
        return {
            "ok": True,
            "status_code": 200,
            "body": {"request_id": "req-remote-999", "status": "IN_QUEUE"},
        }

    with patch("services.video_ai_edit_provider.upload_fal_media_file") as mock_upload:
        with patch.object(provider, "_open_json", side_effect=fake_open_json) as mock_open_json:
            result = provider.submit_video_job(req)

    assert mock_upload.call_count == 0
    assert mock_open_json.call_count == 1
    assert result.ok is True
    assert result.provider_task_id == "req-remote-999"
    assert submitted_payload.get("video_url") == existing_remote_url
    assert submitted_payload.get("num_frames") == 81


# ==============================================================================
# B. CANONICAL PAYLOAD REUSE & WIRE SEMANTICS TESTS
# ==============================================================================

def test_b01_canonical_payload_reuse_and_boundaries(tmp_path: Path, mock_fal_env: dict[str, str]):
    """Verifies canonical build_fal_wan_v2v_payload is reused with exact prompt boundaries."""
    fixture_file = tmp_path / "r16_09_test.mp4"
    fixture_file.write_bytes(b"\x00\x00\x00\x18ftypmp42fake_mp4_bytes")

    fake_hosted_url = "https://fal.media/files/monkey/r16_09_test.mp4"
    long_prompt = "A" * 15_000
    long_negative_prompt = "B" * 10_000

    raw_payload = {
        "prompt": long_prompt,
        "negative_prompt": long_negative_prompt,
        "capability": "video_to_video",
        "source_video_path": str(fixture_file),
        "duration_seconds": 5.0,
        "aspect_ratio": "9:16",
    }

    with patch("services.video_ai_edit_provider.upload_fal_media_file") as mock_upload:
        mock_upload.return_value = {
            "ok": True,
            "file_url": fake_hosted_url,
            "upload_url": "https://fal.storage/upload/xyz",
        }

        wire = _fal_wire_payload(raw_payload, env=mock_fal_env)

        assert mock_upload.call_count == 1
        assert wire["video_url"] == fake_hosted_url
        assert str(fixture_file) not in json.dumps(wire)
        assert wire["num_frames"] == 81
        assert wire["frames_per_second"] == 16
        assert wire["aspect_ratio"] == "9:16"
        # Truncation boundaries defined by build_fal_wan_v2v_payload
        assert len(wire["prompt"]) == 12_000
        assert len(wire["negative_prompt"]) == 8_000


def test_b02_negative_prompt_omitted_when_empty(tmp_path: Path, mock_fal_env: dict[str, str]):
    """When negative_prompt is empty, it must be omitted from canonical wire payload."""
    fixture_file = tmp_path / "r16_09_test2.mp4"
    fixture_file.write_bytes(b"\x00\x00\x00\x18ftypmp42fake_mp4_bytes")

    raw_payload = {
        "prompt": "clean cinematic scene",
        "negative_prompt": "",
        "capability": "video_to_video",
        "source_video_path": str(fixture_file),
        "duration_seconds": 5.0,
    }

    with patch("services.video_ai_edit_provider.upload_fal_media_file") as mock_upload:
        mock_upload.return_value = {
            "ok": True,
            "file_url": "https://fal.media/files/scene2.mp4",
            "upload_url": "https://fal.storage/upload/xyz",
        }
        wire = _fal_wire_payload(raw_payload, env=mock_fal_env)

        assert "negative_prompt" not in wire
        assert wire["prompt"] == "clean cinematic scene"
        assert wire["video_url"] == "https://fal.media/files/scene2.mp4"


def test_b03_storage_upload_calls_counts_under_submit(tmp_path: Path, mock_fal_env: dict[str, str]):
    """End-to-end submit: exactly 1 storage initiate, 1 binary PUT, 1 model queue submit."""
    fixture_file = tmp_path / "scene_fixture.mp4"
    fixture_file.write_bytes(b"\x00\x00\x00\x18ftypmp42video_content")

    provider = _generic_adapter_for("fal_video", mock_fal_env)
    assert isinstance(provider, GenericHttpVideoProvider)

    req = VideoGenerationRequest(
        job_id="test_job_123",
        product_type="video_ai_video_reference",
        prompt="transform scene to cinematic animation",
        required_capability="video_to_video",
        source_video_path=str(fixture_file),
        duration_seconds=5.0,
        ratio="9:16",
        metadata={"source_video_path": str(fixture_file), "required_capability": "video_to_video"},
    )

    initiate_call_count = 0
    put_call_count = 0
    model_submit_call_count = 0
    submitted_payload: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float = 90.0) -> Any:
        nonlocal initiate_call_count, put_call_count, model_submit_call_count, submitted_payload
        url = getattr(request, "full_url", str(request))
        method = getattr(request, "method", "GET")

        if "rest.fal.ai/storage/upload/initiate" in url:
            initiate_call_count += 1
            body = {
                "upload_url": "https://fal.storage.test/v1/put/scene_fixture.mp4",
                "file_url": "https://fal.media/files/tiger/scene_fixture.mp4",
            }
            resp = MagicMock()
            resp.__enter__.return_value = resp
            resp.status = 200
            resp.code = 200
            resp.read.return_value = json.dumps(body).encode("utf-8")
            return resp

        if "fal.storage.test" in url and method == "PUT":
            put_call_count += 1
            resp = MagicMock()
            resp.__enter__.return_value = resp
            resp.status = 200
            resp.code = 200
            resp.read.return_value = b""
            return resp

        if "queue.fal.run" in url:
            model_submit_call_count += 1
            data = getattr(request, "data", b"")
            submitted_payload = json.loads(data.decode("utf-8")) if data else {}
            resp = MagicMock()
            resp.__enter__.return_value = resp
            resp.status = 200
            resp.code = 200
            body = {"request_id": "fal_req_test_888999", "status": "IN_QUEUE"}
            resp.read.return_value = json.dumps(body).encode("utf-8")
            return resp

        raise AssertionError(f"Unexpected URL called: {url}")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = provider.submit_video_job(req)

    assert initiate_call_count == 1
    assert put_call_count == 1
    assert model_submit_call_count == 1

    assert result.ok is True
    assert result.provider_task_id == "fal_req_test_888999"
    assert result.provider_status in {"submitted", "in_queue"}

    # Invariants on wire
    assert submitted_payload.get("video_url") == "https://fal.media/files/tiger/scene_fixture.mp4"
    assert str(fixture_file) not in json.dumps(submitted_payload)
    assert submitted_payload.get("num_frames") == 81
    assert submitted_payload.get("frames_per_second") == 16


# ==============================================================================
# C. TRANSPORT FAILURES & NO-RESUBMIT / NO-RETRY TESTS
# ==============================================================================

def test_c01_upload_initiate_failure_model_submit_zero(tmp_path: Path, mock_fal_env: dict[str, str]):
    """If storage initiate fails, submit aborts immediately: MODEL_SUBMIT=0, no charge."""
    fixture_file = tmp_path / "scene_fail_init.mp4"
    fixture_file.write_bytes(b"\x00\x00\x00\x18ftypmp42video_bytes")

    provider = _generic_adapter_for("fal_video", mock_fal_env)

    req = VideoGenerationRequest(
        job_id="test_job_123",
        product_type="video_ai_video_reference",
        prompt="transform scene",
        required_capability="video_to_video",
        source_video_path=str(fixture_file),
        duration_seconds=5.0,
    )

    model_submit_call_count = 0

    def fake_upload_error(config: Any, local_path: Any, **kwargs: Any) -> Any:
        raise AiEditProviderError("fal_scene_upload_initiate_failed_http_500")

    with patch("services.video_ai_edit_provider.upload_fal_media_file", side_effect=fake_upload_error):
        with patch.object(provider, "_open_json") as mock_open_json:
            result = provider.submit_video_job(req)
            model_submit_call_count = mock_open_json.call_count

    assert model_submit_call_count == 0
    assert result.ok is False
    assert result.provider_status == "contract_blocked"
    assert result.error_code == "fal_scene_upload_initiate_failed_http_500"
    assert result.raw.get("no_charge") is True
    assert result.raw.get("submit_skipped_due_to_contract") is True


def test_c02_upload_put_failure_model_submit_zero(tmp_path: Path, mock_fal_env: dict[str, str]):
    """If storage PUT fails, submit aborts immediately: MODEL_SUBMIT=0, no charge."""
    fixture_file = tmp_path / "scene_fail_put.mp4"
    fixture_file.write_bytes(b"\x00\x00\x00\x18ftypmp42video_bytes")

    provider = _generic_adapter_for("fal_video", mock_fal_env)

    req = VideoGenerationRequest(
        job_id="test_job_123",
        product_type="video_ai_video_reference",
        prompt="transform scene",
        required_capability="video_to_video",
        source_video_path=str(fixture_file),
        duration_seconds=5.0,
    )

    model_submit_call_count = 0

    def fake_upload_put_error(config: Any, local_path: Any, **kwargs: Any) -> Any:
        raise AiEditProviderError("fal_scene_upload_put_failed_http_502")

    with patch("services.video_ai_edit_provider.upload_fal_media_file", side_effect=fake_upload_put_error):
        with patch.object(provider, "_open_json") as mock_open_json:
            result = provider.submit_video_job(req)
            model_submit_call_count = mock_open_json.call_count

    assert model_submit_call_count == 0
    assert result.ok is False
    assert result.provider_status == "contract_blocked"
    assert result.error_code == "fal_scene_upload_put_failed_http_502"
    assert result.raw.get("no_charge") is True


def test_c03_invalid_file_url_model_submit_zero(tmp_path: Path, mock_fal_env: dict[str, str]):
    """If storage returns non-HTTPS URL, submit aborts with contract error: MODEL_SUBMIT=0."""
    fixture_file = tmp_path / "scene_invalid_url.mp4"
    fixture_file.write_bytes(b"\x00\x00\x00\x18ftypmp42video_bytes")

    provider = _generic_adapter_for("fal_video", mock_fal_env)

    req = VideoGenerationRequest(
        job_id="test_job_123",
        product_type="video_ai_video_reference",
        prompt="transform scene",
        required_capability="video_to_video",
        source_video_path=str(fixture_file),
        duration_seconds=5.0,
    )

    model_submit_call_count = 0

    with patch("services.video_ai_edit_provider.upload_fal_media_file") as mock_upload:
        mock_upload.return_value = {
            "ok": True,
            "file_url": "http://insecure.url/file.mp4",  # Not https://
            "upload_url": "https://fal.storage/upload/test",
        }
        with patch.object(provider, "_open_json") as mock_open_json:
            result = provider.submit_video_job(req)
            model_submit_call_count = mock_open_json.call_count

    assert model_submit_call_count == 0
    assert result.ok is False
    assert result.provider_status == "contract_blocked"
    assert result.error_code == "fal_scene_upload_result_url_invalid"


def test_c04_queue_http_4xx_exactly_one_attempt_no_retry(mock_fal_env: dict[str, str]):
    """HTTP 422 from queue must result in exactly 1 attempt, no auto-retry."""
    provider = _generic_adapter_for("fal_video", mock_fal_env)

    req = VideoGenerationRequest(
        job_id="test_job_123",
        product_type="video_ai_video_reference",
        prompt="scene prompt",
        required_capability="video_to_video",
        source_video_path="https://fal.media/files/good.mp4",
        duration_seconds=5.0,
    )

    submit_attempts = 0

    def fake_open_json(url: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        nonlocal submit_attempts
        submit_attempts += 1
        return {
            "ok": False,
            "status_code": 422,
            "body": {"detail": "unprocessable entity"},
            "error": "HTTPError",
        }

    with patch.object(provider, "_open_json", side_effect=fake_open_json):
        result = provider.submit_video_job(req)

    assert submit_attempts == 1
    assert result.ok is False


def test_c05_queue_http_5xx_exactly_one_attempt_no_retry(mock_fal_env: dict[str, str]):
    """HTTP 500 from queue must result in exactly 1 attempt, no auto-retry."""
    provider = _generic_adapter_for("fal_video", mock_fal_env)

    req = VideoGenerationRequest(
        job_id="test_job_123",
        product_type="video_ai_video_reference",
        prompt="scene prompt",
        required_capability="video_to_video",
        source_video_path="https://fal.media/files/good.mp4",
        duration_seconds=5.0,
    )

    submit_attempts = 0

    def fake_open_json(url: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        nonlocal submit_attempts
        submit_attempts += 1
        return {
            "ok": False,
            "status_code": 500,
            "body": {"detail": "internal server error"},
            "error": "HTTPError",
        }

    with patch.object(provider, "_open_json", side_effect=fake_open_json):
        result = provider.submit_video_job(req)

    assert submit_attempts == 1
    assert result.ok is False


def test_c06_ambiguous_timeout_exactly_one_attempt_no_resubmit(mock_fal_env: dict[str, str]):
    """Network timeout during queue submit must result in exactly 1 attempt with no ambiguous resubmit."""
    provider = _generic_adapter_for("fal_video", mock_fal_env)

    req = VideoGenerationRequest(
        job_id="test_job_123",
        product_type="video_ai_video_reference",
        prompt="scene prompt",
        required_capability="video_to_video",
        source_video_path="https://fal.media/files/good.mp4",
        duration_seconds=5.0,
    )

    submit_attempts = 0

    def fake_open_json(url: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        nonlocal submit_attempts
        submit_attempts += 1
        return {
            "ok": False,
            "status_code": 0,
            "body": {},
            "error": "TimeoutError",
            "is_timeout": True,
            "ambiguous_submit": True,
        }

    with patch.object(provider, "_open_json", side_effect=fake_open_json):
        result = provider.submit_video_job(req)

    assert submit_attempts == 1
    assert result.ok is False
    assert result.error_code == "provider_submit_outcome_ambiguous_no_charge"


# ==============================================================================
# D. REGRESSION & CREDENTIAL ISOLATION TESTS
# ==============================================================================

def test_d01_non_fal_providers_payload_building_unchanged(mock_fal_env: dict[str, str]):
    """Generic and ShopAIKey payload builders must remain completely unchanged."""
    req = VideoGenerationRequest(
        job_id="test_job_999",
        product_type="video_ai_video_reference",
        prompt="cinematic scene",
        required_capability="text_to_video",
        duration_seconds=5.0,
    )

    env_with_generic = dict(mock_fal_env)
    env_with_generic["VIDEO_GENERIC_HTTP_MODEL"] = "generic-model-1"
    payload_generic = _build_provider_payload("generic_http", req, env_with_generic)
    assert payload_generic.get("model") == "generic-model-1"
    assert payload_generic.get("source_video_path") == ""

    env_with_shop = dict(mock_fal_env)
    env_with_shop["SHOPAIKEY_VIDEO_MODEL"] = "grok-video-3"
    payload_shop = _build_provider_payload("shopaikey_video", req, env_with_shop)
    assert payload_shop.get("model") == "grok-video-3"


def test_d02_credentials_absent_from_wire_payload_and_debug(mock_fal_env: dict[str, str]):
    """Secret API key must never appear in wire payload or raw debug dictionary."""
    secret = mock_fal_env["FAL_KEY"]
    provider = _generic_adapter_for("fal_video", mock_fal_env)

    req = VideoGenerationRequest(
        job_id="test_job_sec",
        product_type="video_ai_video_reference",
        prompt="cyberpunk neon",
        required_capability="video_to_video",
        source_video_path="https://fal.media/files/scene_sec.mp4",
        duration_seconds=5.0,
    )

    submitted_payload: dict[str, Any] = {}

    def fake_open_json(url: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        nonlocal submitted_payload
        submitted_payload = dict(payload or {})
        return {
            "ok": True,
            "status_code": 200,
            "body": {"request_id": "sec-123", "status": "IN_QUEUE"},
        }

    with patch.object(provider, "_open_json", side_effect=fake_open_json):
        result = provider.submit_video_job(req)

    assert result.ok is True
    assert secret not in json.dumps(submitted_payload)
    # Check debug keys
    raw_str = json.dumps(result.raw)
    assert secret not in raw_str
