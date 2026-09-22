"""Dedicated provider-free test suite for SPEC-PV03B & SPEC-PV03B2 Key4U Kling I2V contract.

Covers invariants A through O:
A. Authoritative image2video endpoint
B. Arbitrary URL transformation forbidden
C. Local image base64 serialization
D. Raw local path absent from wire
E. Missing image fail closed
F. Empty image fail closed
G. kling-v3 duration 5 accepted
H. kling-v3 duration 8 accepted
I. kling-v3 duration 10 accepted
J. 8 remains 8 (no silent rewrite)
K. Unsupported duration fails before submit
L. 9:16 preserved
M. 16:9 preserved
N. 1:1 preserved
O. Unmapped model fails closed / no charge
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import patch

import pytest

from providers import video_generic_http_provider as vgp
from services import video_provider_catalog
from providers.video_generic_http_provider import VideoProviderContractError
from services.video_provider_base import VideoGenerationRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dummy_image(path: Path, content: bytes = b"FAKE_PNG_BINARY_IMAGE_DATA_1234567890") -> Path:
    path.write_bytes(content)
    return path


def _dummy_i2v_payload(
    image_path: str,
    *,
    model_name: str = "kling-v3",
    duration: int = 8,
    ratio: str = "9:16",
    prompt: str = "A cinematic scene",
) -> dict:
    return {
        "capability": "image_to_video",
        "model": "kling-v3",
        "model_name": model_name,
        "image": image_path,
        "duration": duration,
        "aspect_ratio": ratio,
        "prompt": prompt,
        "metadata": {
            "selected_family": "kling",
            "required_capability": "image_to_video",
            "selected_provider": "key4u_video",
        },
    }


# ---------------------------------------------------------------------------
# A. Authoritative image2video endpoint
# ---------------------------------------------------------------------------
def test_case_a_authoritative_image2video_endpoint():
    env = {
        "KEY4U_KLING_I2V_ENDPOINT": "https://api.key4u.vn/kling/v1/videos/image2video",
        "KEY4U_KLING_VIDEO_ENDPOINT": "https://api.key4u.vn/kling/v1/videos/text2video",
    }
    contract = video_provider_catalog.model_interface_contract(
        "key4u_video",
        "kling-v3",
        capability="image_to_video",
        env=env,
    )
    assert contract["submit_url"] == "https://api.key4u.vn/kling/v1/videos/image2video"
    assert "image2video" in contract["submit_url"]
    assert "text2video" not in contract["submit_url"]


# ---------------------------------------------------------------------------
# B. Arbitrary URL transformation forbidden
# ---------------------------------------------------------------------------
def test_case_b_arbitrary_url_transformation_forbidden():
    # If someone configures an arbitrary non-canonical URL on text2video without an explicit I2V endpoint,
    # the system must NOT blindly string-replace 'text2video' with 'image2video'.
    env = {
        "KEY4U_KLING_VIDEO_ENDPOINT": "https://untrusted-arbitrary-domain.com/api/text2video",
    }
    contract = video_provider_catalog.model_interface_contract(
        "key4u_video",
        "kling-v3",
        capability="image_to_video",
        env=env,
    )
    # Must not synthesize https://untrusted-arbitrary-domain.com/api/image2video
    assert "untrusted-arbitrary-domain.com" not in contract.get("submit_url", "")


# ---------------------------------------------------------------------------
# C. Local image base64 serialization
# ---------------------------------------------------------------------------
def test_case_c_local_image_base64_serialization(tmp_path: Path):
    content = b"TEST_PNG_BYTES_FOR_SERIALIZATION"
    img = _make_dummy_image(tmp_path / "source.png", content)

    # Local file -> base64
    serialized = vgp.serialize_local_image_for_provider_wire(str(img))
    assert isinstance(serialized, str)
    decoded = base64.b64decode(serialized)
    assert decoded == content

    # Remote URL preserved as-is
    url = "https://example.com/sample.jpg"
    assert vgp.serialize_local_image_for_provider_wire(url) == url

    # Data URI preserved as-is
    data_uri = "data:image/png;base64," + base64.b64encode(content).decode("ascii")
    assert vgp.serialize_local_image_for_provider_wire(data_uri) == data_uri


# ---------------------------------------------------------------------------
# D. Raw local path absent from wire
# ---------------------------------------------------------------------------
def test_case_d_raw_local_path_absent_from_wire(tmp_path: Path):
    img = _make_dummy_image(tmp_path / "frame.png")
    payload = _dummy_i2v_payload(str(img), model_name="kling-v3", duration=8)

    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert "image" in wire
    wire_image = str(wire["image"])

    # Raw filesystem path must NEVER be sent on wire
    assert str(img) not in wire_image
    assert not wire_image.startswith("/")
    assert not (len(wire_image) >= 2 and wire_image[1] == ":")
    # Must be valid base64
    decoded = base64.b64decode(wire_image)
    assert len(decoded) > 0


# ---------------------------------------------------------------------------
# E. Missing image fail closed
# ---------------------------------------------------------------------------
def test_case_e_missing_image_fail_closed(tmp_path: Path):
    missing_path = str(tmp_path / "does_not_exist.png")

    with pytest.raises(VideoProviderContractError) as exc_info:
        vgp.serialize_local_image_for_provider_wire(missing_path)

    assert exc_info.value.blocker == "provider_image_input_missing_or_invalid"
    assert exc_info.value.debug.get("no_charge") is True


# ---------------------------------------------------------------------------
# F. Empty image fail closed
# ---------------------------------------------------------------------------
def test_case_f_empty_image_fail_closed(tmp_path: Path):
    empty_file = _make_dummy_image(tmp_path / "empty.png", b"")

    with pytest.raises(VideoProviderContractError) as exc_info:
        vgp.serialize_local_image_for_provider_wire(str(empty_file))

    assert exc_info.value.blocker == "provider_image_input_empty"
    assert exc_info.value.debug.get("no_charge") is True


# ---------------------------------------------------------------------------
# G. kling-v3 duration 5 accepted
# ---------------------------------------------------------------------------
def test_case_g_kling_v3_duration_5_accepted(tmp_path: Path):
    img = _make_dummy_image(tmp_path / "img5.png")
    payload = _dummy_i2v_payload(str(img), model_name="kling-v3", duration=5)
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["duration"] == 5


# ---------------------------------------------------------------------------
# H. kling-v3 duration 8 accepted
# ---------------------------------------------------------------------------
def test_case_h_kling_v3_duration_8_accepted(tmp_path: Path):
    img = _make_dummy_image(tmp_path / "img8.png")
    payload = _dummy_i2v_payload(str(img), model_name="kling-v3", duration=8)
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["duration"] == 8


# ---------------------------------------------------------------------------
# I. kling-v3 duration 10 accepted
# ---------------------------------------------------------------------------
def test_case_i_kling_v3_duration_10_accepted(tmp_path: Path):
    img = _make_dummy_image(tmp_path / "img10.png")
    payload = _dummy_i2v_payload(str(img), model_name="kling-v3", duration=10)
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["duration"] == 10


# ---------------------------------------------------------------------------
# J. 8 remains 8 (No silent rewrite)
# ---------------------------------------------------------------------------
def test_case_j_8_remains_8_no_silent_rewrite(tmp_path: Path):
    img = _make_dummy_image(tmp_path / "img_stay8.png")
    payload = _dummy_i2v_payload(str(img), model_name="kling-v3", duration=8)
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["duration"] == 8
    assert wire["duration"] != 5
    assert wire["duration"] != 10


# ---------------------------------------------------------------------------
# K. Unsupported duration fails before submit
# ---------------------------------------------------------------------------
def test_case_k_unsupported_duration_fails_before_submit(tmp_path: Path):
    img = _make_dummy_image(tmp_path / "img_dur.png")

    # kling-v3 with duration 7 (unsupported)
    payload_bad_v3 = _dummy_i2v_payload(str(img), model_name="kling-v3", duration=7)
    with pytest.raises(VideoProviderContractError) as exc_v3:
        vgp._key4u_wire_payload(payload_bad_v3, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert exc_v3.value.blocker == "provider_duration_unsupported_no_charge"
    assert exc_v3.value.debug.get("no_charge") is True

    # kling-v2-6 does not support duration 8 (only 5 and 10)
    payload_bad_v26 = _dummy_i2v_payload(str(img), model_name="kling-v2-6", duration=8)
    with pytest.raises(VideoProviderContractError) as exc_v26:
        vgp._key4u_wire_payload(payload_bad_v26, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert exc_v26.value.blocker == "provider_duration_unsupported_no_charge"
    assert exc_v26.value.debug.get("no_charge") is True


# ---------------------------------------------------------------------------
# L. 9:16 preserved
# ---------------------------------------------------------------------------
def test_case_l_9_16_preserved(tmp_path: Path):
    img = _make_dummy_image(tmp_path / "ratio1.png")
    for r in ("9:16", "9/16", "9x16"):
        payload = _dummy_i2v_payload(str(img), ratio=r, duration=5)
        wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
        assert wire["aspect_ratio"] == "9:16"


# ---------------------------------------------------------------------------
# M. 16:9 preserved
# ---------------------------------------------------------------------------
def test_case_m_16_9_preserved(tmp_path: Path):
    img = _make_dummy_image(tmp_path / "ratio2.png")
    for r in ("16:9", "16/9", "16x9"):
        payload = _dummy_i2v_payload(str(img), ratio=r, duration=5)
        wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
        assert wire["aspect_ratio"] == "16:9"


# ---------------------------------------------------------------------------
# N. 1:1 preserved
# ---------------------------------------------------------------------------
def test_case_n_1_1_preserved(tmp_path: Path):
    img = _make_dummy_image(tmp_path / "ratio3.png")
    for r in ("1:1", "1/1", "1x1"):
        payload = _dummy_i2v_payload(str(img), ratio=r, duration=5)
        wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
        assert wire["aspect_ratio"] == "1:1"


# ---------------------------------------------------------------------------
# O. Unmapped model fails closed / no charge
# ---------------------------------------------------------------------------
def test_case_o_unmapped_model_fails_closed(tmp_path: Path):
    img = _make_dummy_image(tmp_path / "unmapped.png")

    # Internal alias 'kling-video' must NOT be emitted to wire
    payload_alias = _dummy_i2v_payload(str(img), model_name="kling-video", duration=5)
    with pytest.raises(VideoProviderContractError) as exc_alias:
        vgp._key4u_wire_payload(payload_alias, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert exc_alias.value.blocker == "I2V_MODEL_IDENTIFIER_MAPPING_GAP"
    assert exc_alias.value.debug.get("no_charge") is True

    # GenericHttpVideoProvider submit_video_job seam: no network call, returns contract_blocked result
    env = {
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.vn/kling/v1/videos/image2video",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.vn/kling/v1/videos/query?id={task_id}",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test_bearer_token_secret_12345",
        "KEY4U_VIDEO_MODEL": "kling-video",
        "KEY4U_BASE_URL": "https://api.key4u.vn",
        "KEY4U_KLING_VIDEO_ENDPOINT": "https://api.key4u.vn/kling/v1/videos/image2video",
    }
    prov = vgp.GenericHttpVideoProvider(
        provider_name="key4u_video",
        enabled_env="KEY4U_VIDEO_ENABLED",
        submit_url_env="KEY4U_VIDEO_SUBMIT_URL",
        poll_url_env="KEY4U_VIDEO_POLL_URL",
        auth_header_name_env="KEY4U_VIDEO_AUTH_HEADER_NAME",
        auth_header_value_env="KEY4U_VIDEO_AUTH_HEADER_VALUE",
        result_field_env="KEY4U_VIDEO_RESULT_FIELD",
        model_env="KEY4U_VIDEO_MODEL",
        capabilities_env="KEY4U_VIDEO_CAPABILITIES",
        environ=env,
    )
    req = VideoGenerationRequest(
        job_id="test-job-i2v",
        product_type="product_video",
        prompt="Test i2v",
        required_capability="image_to_video",
        metadata={
            "selected_family": "kling",
            "selected_model": "kling-video",
            "model_name": "kling-video",
            "image": str(img),
        },
    )

    with patch("urllib.request.urlopen") as mock_urlopen:
        result = prov.submit_video_job(req)
        assert result.ok is False
        assert result.provider_status == "contract_blocked"
        assert result.error_code == "I2V_MODEL_IDENTIFIER_MAPPING_GAP"
        assert result.raw.get("no_charge") is True
        assert result.raw.get("poll_allowed") is False
        assert mock_urlopen.call_count == 0
