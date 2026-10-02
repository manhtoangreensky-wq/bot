"""Tests for Fal Wan 2.2 V2V Web Worker wire contract remediation (R16.09Q/R).

Ensures local video fixtures are uploaded to Fal storage before model queue submit,
wire contract invariants (num_frames=81 for 5s, 16 fps, hosted https URL) are strictly
enforced, and upload errors fail-closed with 0 model queue submits and 0 wallet mutations.
"""

from __future__ import annotations

import io
import json
import os
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


def test_01_frames_calculation_5s_equals_81():
    """Wan 2.2 frame formula requires (num_frames - 1) % 4 == 0 at 16 fps."""
    frames_5s = calculate_fal_wan_v2v_num_frames(5.0)
    assert frames_5s == 81
    assert (frames_5s - 1) % 4 == 0

    # Boundary checks
    assert calculate_fal_wan_v2v_num_frames(3.0) == 49
    assert (calculate_fal_wan_v2v_num_frames(3.0) - 1) % 4 == 0
    assert calculate_fal_wan_v2v_num_frames(0) == 81  # defaults to 5.0s / 81 frames


def test_02_wire_payload_transforms_local_path_to_remote_https(tmp_path: Path, mock_fal_env: dict[str, str]):
    """_fal_wire_payload uploads local file and returns hosted https URL, never local path."""
    fixture_file = tmp_path / "r16_09_test.mp4"
    fixture_file.write_bytes(b"\x00\x00\x00\x18ftypmp42fake_mp4_bytes")

    fake_hosted_url = "https://fal.media/files/monkey/r16_09_test.mp4"

    raw_payload = {
        "prompt": "make it cinematic gold",
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
        assert wire["prompt"] == "make it cinematic gold"


def test_03_already_remote_video_url_does_not_call_storage(mock_fal_env: dict[str, str]):
    """If source_video_path is already https://, storage upload must be skipped."""
    existing_remote_url = "https://fal.media/files/already_uploaded.mp4"
    raw_payload = {
        "prompt": "cyberpunk style",
        "capability": "video_to_video",
        "source_video_path": existing_remote_url,
        "duration_seconds": 5.0,
    }

    with patch("services.video_ai_edit_provider.upload_fal_media_file") as mock_upload:
        wire = _fal_wire_payload(raw_payload, env=mock_fal_env)
        assert mock_upload.call_count == 0
        assert wire["video_url"] == existing_remote_url
        assert wire["num_frames"] == 81


def test_04_storage_upload_calls_counts_under_submit(tmp_path: Path, mock_fal_env: dict[str, str]):
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


def test_05_upload_initiate_failure_model_submit_zero(tmp_path: Path, mock_fal_env: dict[str, str]):
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


def test_06_upload_put_failure_model_submit_zero(tmp_path: Path, mock_fal_env: dict[str, str]):
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


def test_07_invalid_file_url_model_submit_zero(tmp_path: Path, mock_fal_env: dict[str, str]):
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


def test_08_missing_source_path_model_submit_zero(mock_fal_env: dict[str, str]):
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
