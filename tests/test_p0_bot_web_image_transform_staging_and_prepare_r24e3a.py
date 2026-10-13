"""Targeted contract and unit tests for Canonical Image Staging and Provider-Free Web Image Transform Prepare Seam (R24E3A).

SPEC_ID: BOT-R24E3A-CANONICAL-IMAGE-STAGING-AND-WEB-IMAGE-TRANSFORM-PREPARE
Verifies:
Section 14: Test Matrix — Image Staging
1. Valid PNG accepted
2. Valid JPEG accepted
3. Valid WEBP accepted
4. Invalid PNG magic rejected
5. Invalid JPEG magic rejected
6. Invalid WEBP magic rejected
7. Extension/MIME mismatch rejected
8. Empty image rejected
9. Oversized image rejected (bounded IMAGE_UPLOAD_MAX_MB)
10. Supplied SHA256 mismatch rejected
11. Server-generated opaque upload_id
12. Client-supplied owner ignored/rejected
13. Cross-owner lookup rejected
14. Local path rejected
15. Remote URL rejected
16. Public response contains no local path
17. Existing MP4 upload still passes
18. Existing WAV upload still passes
19. Existing subtitle upload still passes

Section 15: Test Matrix — Image Transform Prepare
A. Missing Core Bridge auth -> reject
B. Invalid signature -> reject
C. Missing actor -> reject
D. Missing upload -> reject
E. Cross-owner upload -> reject
F. Non-image upload -> reject
G. Malformed instruction -> reject
H. Provider injection -> reject
I. Model injection -> reject
J. Price/cost/Xu injection -> reject
K. Valid same-owner image upload -> PREPARED_PROVIDER_DISABLED
L. No provider task ID in prepare response
M. No output URL/result in prepare response
N. No Key4U network call (call_count == 0)
O. KEY4U_PUBLIC_ENABLED remains false
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import bot
from providers.key4u_provider import Key4UProvider
from services.admin_wallet_service import compute_internal_admin_wallet_signature
from services.subdub_upload_staging import (
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_MIME_TYPES,
    get_max_upload_bytes_for_extension,
)


TEST_TOKEN = "test-image-transform-bridge-token"
TEST_SECRET = "test-image-transform-hmac-secret"

# Canonical sample bytes
# Valid 1x1 PNG
SAMPLE_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00"
    b"\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
# Valid 1x1 JPEG
SAMPLE_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
    b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
    b"\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01"
    b"\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01"
    b"\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08"
    b"\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
)
# Valid minimal WEBP
SAMPLE_WEBP_BYTES = (
    b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x000\x01\x00\x9d\x01*\x01\x00"
    b"\x01\x00\x02\x004%\xa4\x00"
)
# Valid MP4 sample
SAMPLE_MP4_BYTES = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free"
# Valid WAV sample
SAMPLE_WAV_BYTES = (
    b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00"
    b"\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
)
# Valid SRT sample
SAMPLE_SRT_BYTES = "1\n00:00:01,000 --> 00:00:03,000\nXin chào TOAN AAS\n".encode("utf-8")


@pytest.fixture(autouse=True)
def setup_isolated_test_env(tmp_path: Path, monkeypatch):
    """Setup isolated test database, staging directory, and bridge credentials."""
    db_file = tmp_path / "test_image_transform.db"
    staging_dir = tmp_path / "staging_media"
    staging_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(bot, "DB_FILE", str(db_file))
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.setenv("SUBDUB_UPLOAD_STAGING_DIR", str(staging_dir))
    monkeypatch.setenv("IMAGE_UPLOAD_MAX_MB", "20")
    monkeypatch.setenv("SUBDUB_UPLOAD_MAX_MB", "50")

    bot.init_db()
    return {"db_file": str(db_file), "staging_dir": str(staging_dir)}


def make_auth_headers(
    method: str,
    path: str,
    body: bytes = b"",
    actor_id: str = "",
    token: str = TEST_TOKEN,
    secret: str = TEST_SECRET,
    timestamp: str | None = None,
    request_id: str | None = None,
) -> dict[str, str]:
    """Helper to compute valid canonical HMAC authentication headers."""
    ts = timestamp if timestamp is not None else str(int(time.time()))
    req_id = request_id if request_id is not None else f"req-test-{time.time_ns()}"
    sig = compute_internal_admin_wallet_signature(
        secret=secret,
        timestamp=ts,
        request_id=req_id,
        method=method,
        path=path,
        body_bytes=body,
        actor_id=actor_id,
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-TOAN-AAS-Signature": sig,
        "X-TOAN-AAS-Timestamp": ts,
        "X-TOAN-AAS-Request-ID": req_id,
        "Content-Type": "application/json",
    }
    if actor_id:
        headers["X-TOAN-AAS-Actor-ID"] = actor_id
    return headers


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 14: TEST MATRIX — IMAGE STAGING
# ══════════════════════════════════════════════════════════════════════════════

def test_14_01_valid_png_accepted():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "file_name": "source_portrait.png",
        "content_type": "image/png",
        "content_base64": base64.b64encode(SAMPLE_PNG_BYTES).decode("ascii"),
        "sha256": hashlib.sha256(SAMPLE_PNG_BYTES).hexdigest(),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["upload_id"].startswith("upl_")
    assert data["file_name"] == "source_portrait.png"
    assert data["content_type"] == "image/png"
    assert data["size_bytes"] == len(SAMPLE_PNG_BYTES)
    assert data["sha256"] == hashlib.sha256(SAMPLE_PNG_BYTES).hexdigest()
    assert "local_path" not in data


def test_14_02_valid_jpeg_accepted():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "file_name": "photo.jpg",
        "content_type": "image/jpeg",
        "content_base64": base64.b64encode(SAMPLE_JPEG_BYTES).decode("ascii"),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["upload_id"].startswith("upl_")
    assert data["content_type"] == "image/jpeg"


def test_14_03_valid_webp_accepted():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "file_name": "graphic.webp",
        "content_type": "image/webp",
        "content_base64": base64.b64encode(SAMPLE_WEBP_BYTES).decode("ascii"),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["upload_id"].startswith("upl_")
    assert data["content_type"] == "image/webp"


def test_14_04_invalid_png_magic_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    fake_png = b"NOT_A_PNG_SIGNATURE_AT_ALL"
    payload = {
        "file_name": "corrupt.png",
        "content_type": "image/png",
        "content_base64": base64.b64encode(fake_png).decode("ascii"),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 400
    assert "INVALID_PNG_SIGNATURE" in resp.json()["error_code"]


def test_14_05_invalid_jpeg_magic_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    fake_jpeg = b"NOT_A_JPEG_FILE"
    payload = {
        "file_name": "corrupt.jpg",
        "content_type": "image/jpeg",
        "content_base64": base64.b64encode(fake_jpeg).decode("ascii"),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 400
    assert "INVALID_JPEG_SIGNATURE" in resp.json()["error_code"]


def test_14_06_invalid_webp_magic_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    fake_webp = b"RIFF\x1a\x00\x00\x00NOTW"
    payload = {
        "file_name": "corrupt.webp",
        "content_type": "image/webp",
        "content_base64": base64.b64encode(fake_webp).decode("ascii"),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 400
    assert "INVALID_WEBP_SIGNATURE" in resp.json()["error_code"]


def test_14_07_extension_mime_mismatch_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    # Claiming image/jpeg for a .png filename with PNG bytes
    payload = {
        "file_name": "mismatch.png",
        "content_type": "image/jpeg",
        "content_base64": base64.b64encode(SAMPLE_PNG_BYTES).decode("ascii"),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 400
    assert "MIME_EXTENSION_MISMATCH" in resp.json()["error_code"]


def test_14_08_empty_image_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "file_name": "empty.png",
        "content_type": "image/png",
        "content_base64": "",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "EMPTY_PAYLOAD"


def test_14_09_oversized_image_rejected(monkeypatch):
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    # Bound image max to 1 MB for testing
    monkeypatch.setenv("IMAGE_UPLOAD_MAX_MB", "1")
    large_payload = SAMPLE_PNG_BYTES + (b"\x00" * (1024 * 1024 + 100))
    payload = {
        "file_name": "oversized.png",
        "content_type": "image/png",
        "content_base64": base64.b64encode(large_payload).decode("ascii"),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 413
    assert "FILE_TOO_LARGE" in resp.json()["error_code"]


def test_14_10_supplied_sha256_mismatch_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "file_name": "mismatch_sha.png",
        "content_type": "image/png",
        "content_base64": base64.b64encode(SAMPLE_PNG_BYTES).decode("ascii"),
        "sha256": "0" * 64,
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "SHA256_MISMATCH"


def test_14_11_server_generated_opaque_upload_id():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "file_name": "opaque_check.png",
        "content_type": "image/png",
        "content_base64": base64.b64encode(SAMPLE_PNG_BYTES).decode("ascii"),
        "upload_id": "client_forged_id_12345",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 200
    returned_id = resp.json()["upload_id"]
    assert returned_id.startswith("upl_")
    assert returned_id != "client_forged_id_12345"


def test_14_12_client_supplied_owner_ignored_or_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "file_name": "owner_forge.png",
        "content_type": "image/png",
        "content_base64": base64.b64encode(SAMPLE_PNG_BYTES).decode("ascii"),
        "user_id": "99999",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "ACTOR_ID_MISMATCH"


def test_14_13_cross_owner_lookup_rejected():
    client = TestClient(bot.fastapi_app)
    actor_a = "10001"
    actor_b = "10002"
    payload = {
        "file_name": "private_photo.png",
        "content_type": "image/png",
        "content_base64": base64.b64encode(SAMPLE_PNG_BYTES).decode("ascii"),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers_a = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor_a)
    resp_a = client.post("/internal/v1/uploads", content=body_bytes, headers=headers_a)
    assert resp_a.status_code == 200
    upload_id = resp_a.json()["upload_id"]

    # Actor B attempts to consume/lookup
    headers_b = make_auth_headers("GET", f"/internal/v1/uploads/{upload_id}", actor_id=actor_b)
    resp_b = client.get(f"/internal/v1/uploads/{upload_id}", headers=headers_b)
    assert resp_b.status_code == 403
    assert resp_b.json()["error_code"] == "FORBIDDEN_CROSS_OWNER"


def test_14_14_local_path_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "file_name": "local.png",
        "content_type": "image/png",
        "content_base64": base64.b64encode(SAMPLE_PNG_BYTES).decode("ascii"),
        "local_path": "/var/data/secret.png",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "LOCAL_PATH_OR_URL_REJECTED"


def test_14_15_remote_url_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "file_name": "remote.png",
        "content_type": "image/png",
        "content_base64": base64.b64encode(SAMPLE_PNG_BYTES).decode("ascii"),
        "remote_url": "https://malicious.site/image.png",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "LOCAL_PATH_OR_URL_REJECTED"


def test_14_16_public_response_contains_no_local_path():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "file_name": "safe_envelope.png",
        "content_type": "image/png",
        "content_base64": base64.b64encode(SAMPLE_PNG_BYTES).decode("ascii"),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "local_path" not in data
    assert "file_path" not in data
    assert "path" not in data

    upload_id = data["upload_id"]
    headers_get = make_auth_headers("GET", f"/internal/v1/uploads/{upload_id}", actor_id=actor)
    resp_get = client.get(f"/internal/v1/uploads/{upload_id}", headers=headers_get)
    assert resp_get.status_code == 200
    data_get = resp_get.json()
    assert "local_path" not in data_get
    assert "file_path" not in data_get
    assert "path" not in data_get


def test_14_17_existing_mp4_upload_still_passes():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "file_name": "video.mp4",
        "content_type": "video/mp4",
        "content_base64": base64.b64encode(SAMPLE_MP4_BYTES).decode("ascii"),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["content_type"] == "video/mp4"


def test_14_18_existing_wav_upload_still_passes():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "file_name": "audio.wav",
        "content_type": "audio/wav",
        "content_base64": base64.b64encode(SAMPLE_WAV_BYTES).decode("ascii"),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["content_type"] == "audio/wav"


def test_14_19_existing_subtitle_upload_still_passes():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "file_name": "subtitles.srt",
        "content_type": "text/plain",
        "content_base64": base64.b64encode(SAMPLE_SRT_BYTES).decode("ascii"),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/uploads", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/uploads", content=body_bytes, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["content_type"] == "text/plain"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 15: TEST MATRIX — IMAGE TRANSFORM PREPARE
# ══════════════════════════════════════════════════════════════════════════════

def test_15_a_missing_core_bridge_auth_rejected():
    client = TestClient(bot.fastapi_app)
    resp = client.post("/internal/v1/web-image-transform/prepare", json={"upload_id": "upl_123"})
    assert resp.status_code in {401, 403}


def test_15_b_invalid_signature_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {"upload_id": "upl_123", "transform_instruction": "enhance"}
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/web-image-transform/prepare", body_bytes, actor_id=actor)
    headers["X-TOAN-AAS-Signature"] = "bad_signature_0000"

    resp = client.post("/internal/v1/web-image-transform/prepare", content=body_bytes, headers=headers)
    assert resp.status_code == 401
    assert "SIGNATURE_INVALID" in resp.json()["error_code"]


def test_15_c_missing_actor_rejected():
    client = TestClient(bot.fastapi_app)
    payload = {"upload_id": "upl_123", "transform_instruction": "enhance"}
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/web-image-transform/prepare", body_bytes, actor_id="")

    resp = client.post("/internal/v1/web-image-transform/prepare", content=body_bytes, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "ACTOR_ID_REQUIRED"


def test_15_d_missing_upload_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {"upload_id": "upl_nonexistent_9999", "transform_instruction": "enhance"}
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/web-image-transform/prepare", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/web-image-transform/prepare", content=body_bytes, headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "UPLOAD_NOT_FOUND"


def test_15_e_cross_owner_upload_rejected():
    client = TestClient(bot.fastapi_app)
    actor_a = "10001"
    actor_b = "10002"

    # Stage upload by actor A
    stage_payload = {
        "file_name": "portrait_a.png",
        "content_type": "image/png",
        "content_base64": base64.b64encode(SAMPLE_PNG_BYTES).decode("ascii"),
    }
    stage_bytes = json.dumps(stage_payload).encode("utf-8")
    stage_headers = make_auth_headers("POST", "/internal/v1/uploads", stage_bytes, actor_id=actor_a)
    stage_resp = client.post("/internal/v1/uploads", content=stage_bytes, headers=stage_headers)
    assert stage_resp.status_code == 200
    upload_id = stage_resp.json()["upload_id"]

    # Actor B attempts to prepare transform using actor A's upload
    prepare_payload = {"upload_id": upload_id, "transform_instruction": "enhance"}
    prepare_bytes = json.dumps(prepare_payload).encode("utf-8")
    prepare_headers = make_auth_headers("POST", "/internal/v1/web-image-transform/prepare", prepare_bytes, actor_id=actor_b)

    resp = client.post("/internal/v1/web-image-transform/prepare", content=prepare_bytes, headers=prepare_headers)
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "FORBIDDEN_CROSS_OWNER"


def test_15_f_non_image_upload_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"

    # Stage MP4 upload
    stage_payload = {
        "file_name": "video.mp4",
        "content_type": "video/mp4",
        "content_base64": base64.b64encode(SAMPLE_MP4_BYTES).decode("ascii"),
    }
    stage_bytes = json.dumps(stage_payload).encode("utf-8")
    stage_headers = make_auth_headers("POST", "/internal/v1/uploads", stage_bytes, actor_id=actor)
    stage_resp = client.post("/internal/v1/uploads", content=stage_bytes, headers=stage_headers)
    assert stage_resp.status_code == 200
    upload_id = stage_resp.json()["upload_id"]

    # Attempt to prepare image transform on MP4 video
    prepare_payload = {"upload_id": upload_id, "transform_instruction": "enhance"}
    prepare_bytes = json.dumps(prepare_payload).encode("utf-8")
    prepare_headers = make_auth_headers("POST", "/internal/v1/web-image-transform/prepare", prepare_bytes, actor_id=actor)

    resp = client.post("/internal/v1/web-image-transform/prepare", content=prepare_bytes, headers=prepare_headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "NON_IMAGE_UPLOAD_REJECTED"


def test_15_g_malformed_instruction_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"

    # Stage valid PNG
    stage_payload = {
        "file_name": "image.png",
        "content_type": "image/png",
        "content_base64": base64.b64encode(SAMPLE_PNG_BYTES).decode("ascii"),
    }
    stage_bytes = json.dumps(stage_payload).encode("utf-8")
    stage_headers = make_auth_headers("POST", "/internal/v1/uploads", stage_bytes, actor_id=actor)
    stage_resp = client.post("/internal/v1/uploads", content=stage_bytes, headers=stage_headers)
    upload_id = stage_resp.json()["upload_id"]

    # 1. Missing/empty instruction
    p1 = {"upload_id": upload_id, "transform_instruction": ""}
    b1 = json.dumps(p1).encode("utf-8")
    h1 = make_auth_headers("POST", "/internal/v1/web-image-transform/prepare", b1, actor_id=actor)
    resp1 = client.post("/internal/v1/web-image-transform/prepare", content=b1, headers=h1)
    assert resp1.status_code == 400
    assert resp1.json()["error_code"] == "TRANSFORM_INSTRUCTION_REQUIRED"

    # 2. Too long instruction (> 1000 chars)
    p2 = {"upload_id": upload_id, "transform_instruction": "A" * 1001}
    b2 = json.dumps(p2).encode("utf-8")
    h2 = make_auth_headers("POST", "/internal/v1/web-image-transform/prepare", b2, actor_id=actor)
    resp2 = client.post("/internal/v1/web-image-transform/prepare", content=b2, headers=h2)
    assert resp2.status_code == 400
    assert resp2.json()["error_code"] == "TRANSFORM_INSTRUCTION_TOO_LONG"

    # 3. Invalid aspect ratio
    p3 = {"upload_id": upload_id, "transform_instruction": "valid", "aspect_ratio": "99:99"}
    b3 = json.dumps(p3).encode("utf-8")
    h3 = make_auth_headers("POST", "/internal/v1/web-image-transform/prepare", b3, actor_id=actor)
    resp3 = client.post("/internal/v1/web-image-transform/prepare", content=b3, headers=h3)
    assert resp3.status_code == 400
    assert resp3.json()["error_code"] == "INVALID_ASPECT_RATIO"


def test_15_h_provider_injection_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "upload_id": "upl_123",
        "transform_instruction": "oil painting",
        "provider": "key4u",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/web-image-transform/prepare", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/web-image-transform/prepare", content=body_bytes, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "AUTHORITY_INJECTION_REJECTED"


def test_15_i_model_injection_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    payload = {
        "upload_id": "upl_123",
        "transform_instruction": "oil painting",
        "model": "grok-imagine-image-pro",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/web-image-transform/prepare", body_bytes, actor_id=actor)

    resp = client.post("/internal/v1/web-image-transform/prepare", content=body_bytes, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "AUTHORITY_INJECTION_REJECTED"


def test_15_j_price_cost_xu_injection_rejected():
    client = TestClient(bot.fastapi_app)
    actor = "10001"
    for forbidden_key in ["price", "cost", "charged_xu", "credits", "wallet", "balance"]:
        payload = {
            "upload_id": "upl_123",
            "transform_instruction": "oil painting",
            forbidden_key: 100,
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        headers = make_auth_headers("POST", "/internal/v1/web-image-transform/prepare", body_bytes, actor_id=actor)

        resp = client.post("/internal/v1/web-image-transform/prepare", content=body_bytes, headers=headers)
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "AUTHORITY_INJECTION_REJECTED"


def test_15_k_to_o_valid_same_owner_image_upload_prepare_provider_disabled():
    client = TestClient(bot.fastapi_app)
    actor = "10001"

    # Stage valid PNG
    stage_payload = {
        "file_name": "target_art.png",
        "content_type": "image/png",
        "content_base64": base64.b64encode(SAMPLE_PNG_BYTES).decode("ascii"),
    }
    stage_bytes = json.dumps(stage_payload).encode("utf-8")
    stage_headers = make_auth_headers("POST", "/internal/v1/uploads", stage_bytes, actor_id=actor)
    stage_resp = client.post("/internal/v1/uploads", content=stage_bytes, headers=stage_headers)
    assert stage_resp.status_code == 200
    upload_id = stage_resp.json()["upload_id"]

    # Spy on Key4UProvider.image_edit to ensure zero provider calls (Clause N)
    with patch.object(Key4UProvider, "image_edit", wraps=getattr(Key4UProvider, "image_edit", None)) as mock_image_edit:
        prepare_payload = {
            "upload_id": upload_id,
            "transform_instruction": "Make the background into a watercolor sunset",
            "aspect_ratio": "16:9",
        }
        prepare_bytes = json.dumps(prepare_payload).encode("utf-8")
        prepare_headers = make_auth_headers("POST", "/internal/v1/web-image-transform/prepare", prepare_bytes, actor_id=actor)

        resp = client.post("/internal/v1/web-image-transform/prepare", content=prepare_bytes, headers=prepare_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Clause K: Valid same-owner image returns PREPARED_PROVIDER_DISABLED
        assert data["ok"] is True
        assert data["status"] == "PREPARED_PROVIDER_DISABLED"
        assert data["status_reason"] == "AWAITING_OWNER_AUTHORIZED_VISIBLE_LIVE_ACCEPTANCE"
        assert data["upload_id"] == upload_id
        assert data["owner_id"] == actor
        assert data["capability"] == "image_transform"
        assert data["executor_owner"] == "bot"
        assert data["provider_family"] == "key4u"
        assert data["provider_executor_implemented"] is True
        assert data["provider_execution_allowed"] is False
        assert data["key4u_public_enabled"] is False
        assert data["key4u_contract_proven"] is True
        assert data["key4u_model_authority_proven"] is False
        assert data["aspect_ratio"] == "16:9"
        assert "Make the background" in data["instruction_sanitized"]
        assert data["media"]["file_name"] == "target_art.png"
        assert data["media"]["content_type"] == "image/png"

        # Clause L: No provider task ID
        assert "task_id" not in data
        assert "provider_task_id" not in data

        # Clause M: No output URL / result
        assert "output_url" not in data
        assert "output" not in data
        assert "result" not in data

        # Clause N: No Key4U network call made
        assert mock_image_edit.call_count == 0

    # Clause O: KEY4U_PUBLIC_ENABLED remains false
    assert bot.KEY4U_PUBLIC_ENABLED is False
